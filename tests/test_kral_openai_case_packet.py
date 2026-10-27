"""Offline stdlib-only tests of the KRAL case packet builder."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import kral_openai_case_packet as tool


class PacketTests(unittest.TestCase):
    def test_prepared_never_sent(self):
        packet = tool.build_packet(case_id="16940096", linked_case="17185949", account_email=None,
                                   user_id=None, request_id=None, extra_context=None)
        self.assertEqual(packet["status"], "PREPARED_NOT_SENT")
        self.assertIn("#17185949", packet["message"])
        self.assertNotIn("deactivated=false", packet["message"])

    def test_no_account_personal_data_hardcoded(self):
        source = Path(tool.__file__).read_text(encoding="utf-8")
        self.assertNotIn("mehmetcerdik457@gmail.com", source)
        self.assertNotIn("user-gD7emuBBFQef3vLrZ803TPH3", source)

    def test_private_atomic_create_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            packet = tool.build_packet(case_id="16940096", linked_case=None, account_email="test@example.com",
                                       user_id=None, request_id=None, extra_context=None)
            output, sha = tool.secure_write(packet, Path(temp) / "cases")
            self.assertEqual(tool.hashlib.sha256(output.read_bytes()).hexdigest(), sha)
            self.assertEqual(json.loads(output.read_text())["status"], "PREPARED_NOT_SENT")
            if os.name == "posix":
                self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                tool.secure_write(packet, Path(temp) / "cases")

    def test_invalid_case_rejected(self):
        with self.assertRaises(Exception):
            tool.case_number("16940096; curl attack.test")

    def test_runtime_environment_not_required(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, {}, clear=True):
                result = tool.main(["--case", "16940096", "--directory", temp])
                self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
