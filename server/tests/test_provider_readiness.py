"""Read-only provider presence evidence. Never put real credentials in tests."""
import json
from pathlib import Path
import tempfile
import unittest
from server import provider_readiness as gate


class ProviderReadinessTests(unittest.TestCase):
    def setUp(self):
        self.flags = {name: "true" for group in gate.PROVIDERS.values() for name in group}

    def test_all_flags_not_equal_credentials_authorized(self):
        result = gate.evaluate(self.flags)
        self.assertEqual(result["mode"], "ALL_FLAGS_PRESENT_UNVERIFIED")
        self.assertEqual(result["real_model_inferences"], 0)
        self.assertEqual(result["credential_values_examined"], 0)
        self.assertFalse(result["credential_validity_attested"])
        self.assertFalse(result["merge_authorized"])

    def test_missing_flag_blocks(self):
        flags = {**self.flags, "OPENAI_KEY_PRESENT": "false"}
        result = gate.evaluate(flags)
        self.assertEqual(result["mode"], "BLOCKED_MISSING_PROVIDER_CONFIG")
        self.assertEqual(result["providers"]["openai"]["missing_flag_names"], ["OPENAI_KEY_PRESENT"])

    def test_all_missing_blocks(self):
        result = gate.evaluate({name: "false" for name in self.flags})
        self.assertTrue(all(x["state"] == "NOT_CONFIGURED" for x in result["providers"].values()))

    def test_untrusted_non_boolean_values_denied(self):
        for value in ("placeholder-sensitive", "TRUE", "1", "", " false ", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                gate.evaluate({**self.flags, "OPENAI_KEY_PRESENT": value})

    def test_unexpected_metadata_denied(self):
        with self.assertRaises(ValueError):
            gate.evaluate({**self.flags, "UNEXPECTED": "true"})

    def test_evidence_private_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "evidence.json"
            gate.write_new(output, gate.evaluate(self.flags))
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(output.read_text())["mode"], "ALL_FLAGS_PRESENT_UNVERIFIED")
            with self.assertRaises(FileExistsError):
                gate.write_new(output, {"mode": "FAKE"})

    def test_symlink_denied(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / "original"
            target.write_text("original")
            alias = root / "evidence.json"
            alias.symlink_to(target)
            with self.assertRaises(ValueError):
                gate.write_new(alias, gate.evaluate(self.flags))
            self.assertEqual(target.read_text(), "original")


if __name__ == "__main__":
    unittest.main()
