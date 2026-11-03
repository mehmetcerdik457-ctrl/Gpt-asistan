"""Task lifecycle tests; synthetic provider only, no paid API or tools."""
import hashlib
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path

from server.task_runtime import TaskManager, EXPERTS


class TestStore:
    def __init__(self, path):
        self.path = str(path)
    def connect(self):
        return sqlite3.connect(self.path, timeout=3)


class FakeProvider:
    def __init__(self, block=False):
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = 0
        self.block = block
    def reply(self, model, prompt):
        self.calls += 1
        self.started.set()
        if self.block:
            self.release.wait(3)
        return "synthetic answer", model, 1


class TaskLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = TestStore(Path(self.tmp.name) / "tasks.sqlite3")
        self.provider = FakeProvider()
        self.manager = TaskManager(self.store, self.provider)

    def tearDown(self):
        self.manager.close()
        self.tmp.cleanup()

    def wait_for(self, task_id, statuses):
        deadline = time.time() + 3
        while time.time() < deadline:
            row = self.manager.get(task_id)
            if row["status"] in statuses:
                return row
            time.sleep(0.01)
        self.fail("task did not reach expected state")

    def test_task_completes_with_hash_evidence_and_no_tool_execution(self):
        task = self.manager.submit("model-fixture", "model-fixture", "ai-ml-engineer", "Review adapter")
        completed = self.wait_for(task["task_id"], {"completed"})
        self.assertEqual(completed["result"], "synthetic answer")
        self.assertEqual(completed["result_sha256"], hashlib.sha256(b"synthetic answer").hexdigest())
        self.assertEqual((completed["tools_executed"], completed["external_actions"]), (0, 0))

    def test_cancel_running_task_suppresses_late_result(self):
        provider = FakeProvider(block=True)
        manager = TaskManager(self.store, provider)
        try:
            task = manager.submit("model-fixture", "model-fixture", "test-engineer", "Long task")
            self.assertTrue(provider.started.wait(1))
            cancelling = manager.cancel(task["task_id"])
            self.assertTrue(cancelling["cancel_requested"])
            self.assertEqual(cancelling["status"], "running")
            provider.release.set()
            cancelled = self.wait_for_with(manager, task["task_id"], {"cancelled"})
            self.assertIsNone(cancelled["result"])
        finally:
            provider.release.set()
            manager.close()

    def wait_for_with(self, manager, task_id, statuses):
        deadline = time.time() + 3
        while time.time() < deadline:
            row = manager.get(task_id)
            if row["status"] in statuses:
                return row
            time.sleep(0.01)
        self.fail("task did not reach expected state")

    def test_critical_task_requires_signed_owner_approval_and_never_executes(self):
        task = self.manager.submit("model-fixture", "model-fixture", "security-auditor",
                                   "Review proposed deployment", approval_required=True)
        self.assertEqual(task["status"], "awaiting_approval")
        approved = self.manager.approve(task["task_id"])
        self.assertEqual(approved["status"], "approved_not_executed")
        self.assertEqual(self.provider.calls, 0)
        self.assertEqual(approved["external_actions"], 0)

    def test_unknown_expert_rejected(self):
        with self.assertRaisesRegex(ValueError, "TASK_EXPERT_NOT_FOUND"):
            self.manager.submit("m", "m", "unknown", "hello")

    def test_restart_marks_nonterminal_tasks_failed(self):
        task = self.manager.submit("model-fixture", "model-fixture", "chief-engineer", "Task")
        self.wait_for(task["task_id"], {"completed"})
        with self.store.connect() as db:
            db.execute("UPDATE owner_tasks SET status='running' WHERE task_id=?", (task["task_id"],))
        restarted = TaskManager(self.store, self.provider)
        try:
            self.assertEqual(restarted.get(task["task_id"])["status"], "failed")
            self.assertEqual(restarted.get(task["task_id"])["error"], "PROCESS_RESTARTED")
        finally:
            restarted.close()


if __name__ == "__main__":
    unittest.main()
