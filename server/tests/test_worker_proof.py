"""Safety and status contracts for the real read-only runner probes."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from server import worker_proof as worker


class WorkerProofTests(unittest.TestCase):
    def test_exact_eight_roles_and_fifty_logical_slots(self):
        self.assertEqual(len(worker.ROLE_TESTS), 8)
        self.assertEqual(worker.mission_control.MAX_WORKERS, 50)

    def test_denies_arbitrary_command_roles(self):
        with self.assertRaisesRegex(ValueError, "ROLE_NOT_ALLOWLISTED"):
            worker.execute_role("rm -rf .", network_probe=lambda: "LIVE_PUBLIC_GITHUB_READ")

    def test_real_process_is_not_marked_as_ai_model(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            p = root / ".github" / "agents" / "test-engineer.agent.md"
            p.parent.mkdir(parents=True)
            p.write_text("---\nname: Test Engineer\n---\n", encoding="utf-8")
            finished = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")
            with patch.object(worker, "ROOT", root), patch.object(
                    worker.subprocess, "run", return_value=finished) as run, patch.dict(
                    os.environ, {"GITHUB_TOKEN": "SENSITIVE_SHOULD_NOT_PASS"}, clear=False):
                row = worker.execute_role(
                    "test-engineer", network_probe=lambda: "LIVE_PUBLIC_GITHUB_READ")
            self.assertEqual(row["mode"], "REAL_PROCESS_PROBE_PASS_NO_MODEL")
            self.assertEqual(row["real_ai_model_calls"], 0)
            self.assertEqual(row["code_changes"], 0)
            self.assertEqual(row["logical_worker_slot_capacity"], 50)
            self.assertNotIn("GITHUB_TOKEN", run.call_args.kwargs["env"])
            self.assertFalse(run.call_args.kwargs.get("shell", False))

    def test_network_failure_stays_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            p = root / ".github" / "agents" / "test-engineer.agent.md"
            p.parent.mkdir(parents=True)
            p.write_text("---\nname: Test Engineer\n---\n", encoding="utf-8")
            finished = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")
            with patch.object(worker, "ROOT", root), patch.object(
                    worker.subprocess, "run", return_value=finished):
                row = worker.execute_role(
                    "test-engineer", network_probe=lambda: "BLOCKED_NETWORK_OR_GITHUB")
            self.assertEqual(row["mode"], "BLOCKED_OR_PARTIAL_NO_MODEL")

    def test_profile_symlink_denied(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            p = root / ".github" / "agents" / "test-engineer.agent.md"
            p.parent.mkdir(parents=True)
            original = root / "real-agent.md"
            original.write_text("---\nname: test\n---\n", encoding="utf-8")
            p.symlink_to(original)
            with patch.object(worker, "ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "AGENT_PROFILE_UNAVAILABLE"):
                    worker.execute_role("test-engineer", network_probe=lambda: "LIVE_PUBLIC_GITHUB_READ")


if __name__ == "__main__":
    unittest.main()
