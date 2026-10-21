import os
import tempfile
import unittest
from pathlib import Path

from server.secure_sqlite import secure_sqlite_file


class SecureSqlitePathTests(unittest.TestCase):
    def test_existing_file_is_restricted_to_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private.sqlite3"
            path.touch()
            path.chmod(0o644)
            self.assertEqual(secure_sqlite_file(path), str(path))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_symlink_is_rejected_without_modifying_target(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target.sqlite3"
            target.write_bytes(b"unchanged")
            link = Path(directory) / "link.sqlite3"
            link.symlink_to(target)
            with self.assertRaises(OSError):
                secure_sqlite_file(link)
            self.assertEqual(target.read_bytes(), b"unchanged")

    def test_group_or_world_writable_parent_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory) / "unsafe"
            parent.mkdir()
            parent.chmod(0o777)
            try:
                with self.assertRaises(ValueError):
                    secure_sqlite_file(parent / "private.sqlite3")
            finally:
                parent.chmod(0o700)

    def test_relative_path_is_rejected(self):
        with self.assertRaises(ValueError):
            secure_sqlite_file("relative.sqlite3")


if __name__ == "__main__":
    unittest.main()
