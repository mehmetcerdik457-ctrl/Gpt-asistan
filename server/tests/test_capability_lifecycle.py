"""Live local filesystem/SQLite fixture tests; no model or device involved."""
import hashlib
import json
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile

from server import capability_lifecycle as c


def recipe(**kw):
    data = {"version": 1, "id": "status.filter",
            "operation": "text.filter_lines", "needle": "ERROR",
            "case_sensitive": False, "limit": 5}
    data.update(kw)
    return json.dumps(data).encode()


class ReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.src = self.root / "recipe.json"
        self.src.write_bytes(recipe())
        self.digest = hashlib.sha256(self.src.read_bytes()).hexdigest()
        self.db = self.root / "local.sqlite3"
        self.registry = c.Registry(self.db)

    def register(self):
        return self.registry.register(self.src, self.digest)

    def test_two_independent_tasks_and_restart_reuse(self):
        self.assertEqual(self.register()["status"], "REGISTERED_DISABLED")
        with self.assertRaisesRegex(c.Refused, "DISABLED"):
            self.registry.run("status.filter", self.src)
        self.registry.switch("status.filter", self.digest, True)
        a, b = self.root / "first.log", self.root / "next.log"
        a.write_text("ok\nERROR one\n")
        b.write_text("error two\nnormal\n")
        first = self.registry.run("status.filter", a)
        second = c.Registry(self.db).run("status.filter", b)
        self.assertEqual(first["lines"], ["ERROR one"])
        self.assertEqual(second["lines"], ["error two"])
        self.assertNotEqual(first["input_sha256"], second["input_sha256"])
        self.assertEqual(second["external_actions"], 0)

    def test_disable_rolls_back_without_losing_source_record(self):
        self.register()
        self.registry.switch("status.filter", self.digest, True)
        self.registry.switch("status.filter", self.digest, False)
        self.assertEqual(c.Registry(self.db).listing()[0]["status"], "DISABLED")
        with self.assertRaisesRegex(c.Refused, "DISABLED"):
            self.registry.run("status.filter", self.src)

    def test_wrong_source_hash_rejected(self):
        with self.assertRaisesRegex(c.Refused, "SOURCE_DIGEST_MISMATCH"):
            self.registry.register(self.src, "0" * 64)
        self.assertEqual(self.registry.listing(), [])
        self.register()
        with self.assertRaisesRegex(c.Refused, "SHA_NOT_FOUND"):
            self.registry.switch("status.filter", "0" * 64, True)

    def test_source_change_requires_new_capability_id(self):
        self.register()
        self.src.write_bytes(recipe(needle="WARN"))
        different = hashlib.sha256(self.src.read_bytes()).hexdigest()
        with self.assertRaisesRegex(c.Refused, "CONFLICT"):
            self.registry.register(self.src, different)
        self.assertEqual(self.registry.listing()[0]["source_sha256"], self.digest)

    def test_invalid_operations_and_types_fail_closed(self):
        for bad in ({"operation": "shell"}, {"limit": 999}, {"limit": True},
                    {"case_sensitive": "yes"}, {"needle": ""}, {"id": "../evasion"}):
            with self.subTest(bad=bad):
                self.src.write_bytes(recipe(**bad))
                d = hashlib.sha256(self.src.read_bytes()).hexdigest()
                with self.assertRaises(c.Refused):
                    self.registry.register(self.src, d)
        self.assertEqual(self.registry.listing(), [])

    def test_reject_duplicate_json_fields(self):
        self.src.write_bytes(b'{"version":1,"version":1}')
        with self.assertRaisesRegex(c.Refused, "DUPLICATE"):
            self.registry.register(self.src, hashlib.sha256(self.src.read_bytes()).hexdigest())

    def test_zip_and_symlink_never_become_skills(self):
        alias = self.root / "alias.json"
        alias.symlink_to(self.src)
        with self.assertRaises(c.Refused):
            self.registry.register(alias, self.digest)
        archive = self.root / "source.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("recipe.json", recipe())
        with self.assertRaisesRegex(c.Refused, "NOT_DECLARATIVE"):
            self.registry.register(archive, hashlib.sha256(archive.read_bytes()).hexdigest())

    def test_private_db_permission_and_symlink(self):
        self.assertEqual(stat.S_IMODE(self.db.stat().st_mode), 0o600)
        alias = self.root / "alias.db"
        alias.symlink_to(self.db)
        with self.assertRaisesRegex(c.Refused, "PRIVATE_DB_PATH"):
            c.Registry(alias)

    def test_input_limits_and_output_truncation(self):
        self.register()
        self.registry.switch("status.filter", self.digest, True)
        data = self.root / "input.txt"
        data.write_bytes(b"ERROR\x00")
        with self.assertRaisesRegex(c.Refused, "BINARY"):
            self.registry.run("status.filter", data)
        data.write_bytes(b"x" * 65537)
        with self.assertRaisesRegex(c.Refused, "SIZE"):
            self.registry.run("status.filter", data)
        data.write_text("\n".join(["ERROR " + "A" * 1000] * 10))
        result = self.registry.run("status.filter", data)
        self.assertTrue(result["truncated"])
        self.assertLessEqual(sum(len(s) for s in result["lines"]), 4096)

    def test_existing_registration_does_not_reset_enabled_state(self):
        self.register()
        self.registry.switch("status.filter", self.digest, True)
        self.register()
        self.assertEqual(self.registry.listing()[0]["status"], "ENABLED")


if __name__ == "__main__":
    unittest.main()
