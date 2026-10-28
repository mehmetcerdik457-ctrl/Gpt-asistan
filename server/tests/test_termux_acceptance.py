"""Tests for read-only Termux acceptance evidence, without a real device."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from server import termux_acceptance as t


class FakeBackend:
    def __init__(self, response="Local answer"):
        self.inferences = 0
        self.response = response

    def validate_backend(self, config):
        if config.get("endpoint") != "http://127.0.0.1:11434/v1":
            raise ValueError("LOCALHOST_ONLY")

    def probe(self, config):
        if config["model"] == "not-installed":
            raise ValueError("REQUESTED_MODEL_NOT_INSTALLED")
        return {config["model"], config["supervisor_model"]}

    def infer(self, *args):
        self.inferences += 1
        assert args[2] == "test-engineer"
        assert args[3] == "worker-01"
        return self.response


class TermuxAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.provider = {"endpoint": "http://127.0.0.1:11434/v1",
                         "model": "qwen3:1.7b", "supervisor_model": "qwen3:1.7b"}

    def test_catalog_only_does_not_infer_or_claim_device(self):
        backend = FakeBackend()
        with patch.dict(os.environ, {"PREFIX": "/other/location"}):
            result = t.assess(self.provider, backend=backend)
        self.assertEqual(result["mode"], "LOCAL_CATALOG_PASS_NO_INFERENCE")
        self.assertEqual(backend.inferences, 0)
        self.assertEqual(result["runtime_hint"], "RUNTIME_NOT_ATTESTED")
        self.assertEqual(result["github_writes"], 0)
        self.assertFalse(result["model_binary_identity_attested"])

    def test_real_inference_keeps_response_private(self):
        backend = FakeBackend("VERY_PRIVATE_OUTPUT")
        result = t.assess(self.provider, infer=True, backend=backend)
        self.assertEqual(backend.inferences, 1)
        self.assertEqual(result["mode"], "LOCAL_INFERENCE_RESPONSE_PASS_NOT_TASK_COMPLETION")
        self.assertEqual(result["repository_tasks_completed"], 0)
        self.assertEqual(result["response_bytes"], len(b"VERY_PRIVATE_OUTPUT"))
        self.assertEqual(len(result["response_sha256"]), 64)
        self.assertNotIn("VERY_PRIVATE_OUTPUT", json.dumps(result))

    def test_uninstalled_model_and_external_endpoint_fail_closed(self):
        for wrong in ({**self.provider, "model": "not-installed"},
                      {**self.provider, "endpoint": "http://evil.example:11434/v1"}):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                t.assess(wrong, infer=True, backend=FakeBackend())

    def test_private_evidence_file_created_once_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "evidence.json"
            t.write_new_private(output, '{"status":"PASS"}\n')
            self.assertEqual(json.loads(output.read_text()), {"status": "PASS"})
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                t.write_new_private(output, "OVERWRITE")
            self.assertNotIn("OVERWRITE", output.read_text())

    def test_symlink_input_and_evidence_denied(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = root / "real.json"
            original.write_text(json.dumps(self.provider))
            link = root / "provider.json"
            link.symlink_to(original)
            with self.assertRaises(ValueError):
                t.read_provider(link)
            with self.assertRaises(ValueError):
                t.write_new_private(link, "NO")
            self.assertEqual(json.loads(original.read_text()), self.provider)

    def test_config_size_limited_and_regular_file_allowed(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "provider.json"
            p.write_text(json.dumps(self.provider))
            self.assertEqual(t.read_provider(p), self.provider)
            p.write_text("X" * (t.MAX_CONFIG_BYTES + 1))
            with self.assertRaises(ValueError):
                t.read_provider(p)


if __name__ == "__main__":
    unittest.main()
