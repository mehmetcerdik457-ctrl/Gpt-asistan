"""Offline regression of restored legacy KRAL model-fleet and YouTube MCP.

Runs original source tests in isolated Python processes. These are only local
mock/loopback tests, NOT evidence that YouTube OAuth or model API is connected.
"""
import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]


class LegacyRecoveryTests(unittest.TestCase):
    def check_original_suite(self, relative_dir):
        env = os.environ.copy()
        for key in ("OPENAI_API_KEY", "HUGGINGFACE_TOKEN", "HF_TOKEN",
                    "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN",
                    "YOUTUBE_ACCESS_TOKEN", "YOUTUBE_CLIENT_ID"):
            env.pop(key, None)
        env["YOUTUBE_WRITE_ENABLED"] = "false"
        env["KRAL_PROVIDER"] = "auto"
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", relative_dir,
             "-p", "test_*.py", "-v"],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=100,
            check=False
        )
        self.assertEqual(
            result.returncode, 0,
            "Recovered offline suite failed: " + relative_dir + "\n" +
            (result.stdout + result.stderr)[-4500:]
        )

    def test_youtube_mcp_original_tests(self):
        self.check_original_suite("kral/mcp")

    def test_model_fleet_original_tests(self):
        self.check_original_suite("legacy/kral/safe")

    def test_no_model_or_youtube_secrets_in_repository(self):
        import hashlib
        expected_blobs = {
            "kral/mcp/youtube_server.py": "35559cd8d213d13d15b87625fff991ec0a66f0c0",
            "kral/mcp/test_youtube_server.py": "a30252626431b1c4c31176483df6b8dbb9995445",
            "legacy/kral/safe/fleet.py": "f1531cd60ab27932ec11e4999877b122454970a3",
            "legacy/kral/safe/assistant.py": "43d204cce304f136cab4f29a24e2370e77994deb",
        }
        for path, sha in expected_blobs.items():
            with self.subTest(file=path):
                raw = (ROOT / path).read_bytes()
                blob = b"blob " + str(len(raw)).encode() + b"\x00" + raw
                self.assertEqual(hashlib.sha1(blob).hexdigest(), sha)


if __name__ == "__main__":
    unittest.main()
