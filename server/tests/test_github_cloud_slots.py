"""No GitHub API or model calls; controlled tests of 50 hosted process slots."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from server import github_cloud_slots as cloud

SHA = "a" * 40
RUN = "123456789"


def proof(slot: int) -> dict:
    return {
        "cloud_slot_schema": 1,
        "schema": 1,
        "slot": slot,
        "worker_id": f"worker-{slot:02d}",
        "role": cloud.role_for_slot(slot),
        "execution_type": "GITHUB_ACTIONS_READONLY_PROCESS_NOT_AI",
        "mode": "REAL_PROCESS_PROBE_PASS_NO_MODEL",
        "test_result": "PASS",
        "github_read": "LIVE_PUBLIC_GITHUB_READ",
        "github_actions_run_id": RUN,
        "source_sha": SHA,
        "logical_worker_slot_capacity": 50,
        "real_ai_model_calls": 0,
        "code_changes": 0,
        "owner_acceptance": "NOT_GRANTED",
        "profile_sha256": "b" * 64,
        "test_output_sha256": "c" * 64,
    }


class CloudSlotTests(unittest.TestCase):
    def setup_directory(self, root: Path):
        for slot in range(1, 51):
            folder = root / f"kral-cloud-slot-{slot}"
            folder.mkdir()
            (folder / "kral-cloud-slot.json").write_text(json.dumps(proof(slot)))

    def test_fifty_distinct_fixed_roles(self):
        self.assertEqual(len({f"worker-{n:02d}" for n in range(1, 51)}), 50)
        self.assertEqual(cloud.role_for_slot(1), "github-master-ai")
        self.assertEqual(cloud.role_for_slot(50), "chief-engineer")
        self.assertEqual(len(cloud.ROLES), 8)

    def test_reject_invalid_slots(self):
        for slot in [0, -1, 51, True, "1", None, 100]:
            with self.subTest(slot=slot), self.assertRaises(cloud.InvalidEvidence):
                cloud.role_for_slot(slot)

    def test_role_process_proof_pass_without_model(self):
        def role_runner(role):
            return {**proof(1), "role": role}
        p = cloud.run_slot(1, execute_role=role_runner)
        self.assertEqual(p["worker_id"], "worker-01")
        self.assertEqual(p["real_ai_model_calls"], 0)

    def test_reject_fake_model_session_or_failed_probe(self):
        for changed in [{"real_ai_model_calls": 1}, {"code_changes": 1},
                        {"mode": "BLOCKED_OR_PARTIAL_NO_MODEL"}]:
            with self.subTest(changed=changed):
                with self.assertRaises(cloud.InvalidEvidence):
                    cloud.run_slot(1, execute_role=lambda _: {**proof(1), **changed})

    def test_verified_fifty_artifacts(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            self.setup_directory(root)
            r = cloud.verify_all(root, expected_sha=SHA, expected_run_id=RUN)
            self.assertEqual(r["verified_process_slots"], 50)
            self.assertEqual(r["copilot_sessions_started"], 0)

    def test_missing_extra_and_wrong_slot_fail_closed(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            self.setup_directory(root)
            (root / "kral-cloud-slot-50" / "kral-cloud-slot.json").unlink()
            with self.assertRaises(cloud.InvalidEvidence):
                cloud.verify_all(root, expected_sha=SHA, expected_run_id=RUN)
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            self.setup_directory(root)
            (root / "extra").mkdir()
            with self.assertRaises(cloud.InvalidEvidence):
                cloud.verify_all(root, expected_sha=SHA, expected_run_id=RUN)
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            self.setup_directory(root)
            path = root / "kral-cloud-slot-1" / "kral-cloud-slot.json"
            path.write_text(json.dumps({**proof(1), "source_sha": "bad"}))
            with self.assertRaises(cloud.InvalidEvidence):
                cloud.verify_all(root, expected_sha=SHA, expected_run_id=RUN)

    def test_symlink_artifact_denied(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            self.setup_directory(root)
            path = root / "kral-cloud-slot-3" / "kral-cloud-slot.json"
            target = root / "copy"
            target.write_bytes(path.read_bytes())
            path.unlink()
            path.symlink_to(target)
            with self.assertRaises(cloud.InvalidEvidence):
                cloud.verify_all(root, expected_sha=SHA, expected_run_id=RUN)

    def test_wrong_provenance_denied(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            self.setup_directory(root)
            with self.assertRaises(cloud.InvalidEvidence):
                cloud.verify_all(root, expected_sha="invalid", expected_run_id=RUN)
            with self.assertRaises(cloud.InvalidEvidence):
                cloud.verify_all(root, expected_sha=SHA, expected_run_id="bogus")

    def test_secure_no_overwrite(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            output = root / "new.json"
            cloud.write_exclusive(output, proof(1))
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                cloud.write_exclusive(output, {"malicious": True})
            self.assertNotIn("malicious", output.read_text())


if __name__ == "__main__":
    unittest.main()
