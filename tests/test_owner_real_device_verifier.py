import copy
import json
import pathlib
import tempfile
import unittest
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
import verify_owner_real_device as verifier

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO_EXPECTED = ROOT / "control-plane/runtime/owner_real_device_expected.json"
SIGNED_HASH = "a" * 64

def frozen_expected():
    data = json.loads(REPO_EXPECTED.read_text(encoding="utf-8"))
    data["status"] = "SIGNED_ARTIFACT_IDENTITY_FROZEN"
    data["artifact_sha256"] = SIGNED_HASH
    return data

def valid_evidence(expected):
    return {
        "version": 1,
        "status": "REAL_DEVICE_EVIDENCE_CAPTURED",
        "git_head": expected["target_head"],
        "captured_at_epoch_ms": 1,
        "evidence": {
            "device_model": "TEST DEVICE",
            "android_version": "TEST",
            "package_name": expected["package_name"],
            "version_name": expected["version_name"],
            "version_code": expected["version_code"],
            "artifact_sha256": expected["artifact_sha256"],
            "signer_cert_sha256": expected["expected_signer_cert_sha256"],
            "install_result": "PASS",
            "launch_result": "PASS",
            "postcondition_result": "PASS",
        },
        "phone_agent": {
            "implementation": expected["runtime_implementation"],
            "accessibility_enabled": True,
            "service_connected": True,
            "network_permission": "NONE",
            "self_test_target_hits": 1,
            "tap_pass": True,
            "click_text_pass": True,
            "scroll_forward_pass": True,
            "runtime_postcondition_result": "PASS",
            "events": [
                {"action": "SERVICE", "status": "READY"},
                {"action": "TAP", "status": "PASS"},
                {"action": "CLICK_TEXT", "status": "PASS"},
                {"action": "SCROLL_FORWARD", "status": "PASS"},
            ],
        },
    }

class OwnerRealDeviceVerifierTests(unittest.TestCase):
    def _write_json(self, folder, name, data):
        path = pathlib.Path(folder) / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_repository_contract_fails_closed_until_signed_hash_frozen(self):
        expected = json.loads(REPO_EXPECTED.read_text(encoding="utf-8"))
        evidence = valid_evidence({**expected, "artifact_sha256": SIGNED_HASH})
        with tempfile.TemporaryDirectory() as td:
            evidence_path = self._write_json(td, "evidence.json", evidence)
            with self.assertRaises(SystemExit):
                verifier.validate(evidence_path, REPO_EXPECTED)

    def test_valid_frozen_contract_passes(self):
        expected = frozen_expected()
        evidence = valid_evidence(expected)
        with tempfile.TemporaryDirectory() as td:
            expected_path = self._write_json(td, "expected.json", expected)
            evidence_path = self._write_json(td, "evidence.json", evidence)
            result = verifier.validate(evidence_path, expected_path)
        self.assertEqual(result["status"], "OWNER_REAL_DEVICE_EVIDENCE_VERIFIED")
        self.assertEqual(result["artifact_sha256"], SIGNED_HASH)

    def test_wrong_signer_is_rejected(self):
        expected = frozen_expected()
        evidence = valid_evidence(expected)
        evidence["evidence"]["signer_cert_sha256"] = "b" * 64
        with tempfile.TemporaryDirectory() as td:
            expected_path = self._write_json(td, "expected.json", expected)
            evidence_path = self._write_json(td, "evidence.json", evidence)
            with self.assertRaises(SystemExit):
                verifier.validate(evidence_path, expected_path)

    def test_missing_scroll_event_is_rejected(self):
        expected = frozen_expected()
        evidence = valid_evidence(expected)
        evidence["phone_agent"]["events"] = [
            e for e in evidence["phone_agent"]["events"]
            if e["action"] != "SCROLL_FORWARD"
        ]
        with tempfile.TemporaryDirectory() as td:
            expected_path = self._write_json(td, "expected.json", expected)
            evidence_path = self._write_json(td, "evidence.json", evidence)
            with self.assertRaises(SystemExit):
                verifier.validate(evidence_path, expected_path)

if __name__ == "__main__":
    unittest.main()
