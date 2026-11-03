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
        self.last_request_metadata = None
        self.last_client_request_id = None
    def reply(self, model, prompt):
        self.calls += 1
        self.started.set()
        if self.block:
            self.release.wait(3)
        return "synthetic answer", model, 1
    def reply_with_metadata(self, model, prompt, *, request_metadata=None, client_request_id=None):
        self.last_request_metadata = request_metadata
        self.last_client_request_id = client_request_id
        answer, actual, elapsed = self.reply(model, prompt)
        return answer, actual, elapsed, {
            "response_id": "resp_synthetic_123",
            "request_id": "req_synthetic_123",
            "http_status": 200,
            "provider_error_code": None,
            "retryable": False,
            "retry_after_seconds": None,
        }


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
        self.assertEqual(completed["response_id"], "resp_synthetic_123")
        self.assertEqual(completed["provider_request_id"], "req_synthetic_123")
        self.assertEqual(completed["provider_http_status"], 200)
        self.assertFalse(completed["retryable"])
        self.assertEqual(completed["client_request_id"], task["task_id"])
        self.assertEqual(self.provider.last_client_request_id, task["task_id"])
        self.assertEqual(self.provider.last_request_metadata, {
            "kral_task_id": task["task_id"], "kral_expert": "ai-ml-engineer", "kral_runtime": "v1"
        })

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

    def test_cancel_while_waiting_for_shared_slot_never_calls_provider(self):
        slots = threading.BoundedSemaphore(1)
        slots.acquire()
        slot_held = True
        provider = FakeProvider()
        manager = TaskManager(self.store, provider, slots)
        try:
            task = manager.submit("model-fixture", "model-fixture", "test-engineer", "Waiting task")
            self.wait_for_with(manager, task["task_id"], {"running"})
            manager.cancel(task["task_id"])
            self.assertEqual(provider.calls, 0)
            slots.release()
            slot_held = False
            result = self.wait_for_with(manager, task["task_id"], {"cancelled"})
            self.assertEqual(provider.calls, 0)
            self.assertIsNone(result["result"])
        finally:
            if slot_held:
                slots.release()
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

    def test_awaiting_approval_task_can_be_cancelled(self):
        task = self.manager.submit("model-fixture", "model-fixture", "security-auditor",
                                   "Critical action", approval_required=True)
        cancelled = self.manager.cancel(task["task_id"])
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(self.provider.calls, 0)

    def test_retryable_provider_failure_is_recorded_without_automatic_replay(self):
        class ProviderFailure(Exception):
            code = "PROVIDER_QUOTA_OR_RATE_LIMIT"
            provider_request_id = "req_rate_limit"
            provider_http_status = 429
            provider_error_code = "rate_limit_exceeded"
            retryable = True
            retry_after_seconds = 7
        class FailingProvider:
            calls = 0
            def reply_with_metadata(self, model, prompt, *, request_metadata=None, client_request_id=None):
                self.calls += 1
                raise ProviderFailure("redacted")
        provider = FailingProvider()
        manager = TaskManager(self.store, provider)
        try:
            task = manager.submit("model-fixture", "model-fixture", "test-engineer", "Rate limited task")
            failed = self.wait_for_with(manager, task["task_id"], {"failed"})
            self.assertEqual(provider.calls, 1, "a POST must not be replayed automatically")
            self.assertEqual(failed["provider_http_status"], 429)
            self.assertEqual(failed["provider_error_code"], "rate_limit_exceeded")
            self.assertEqual(failed["provider_request_id"], "req_rate_limit")
            self.assertTrue(failed["retryable"])
            self.assertEqual(failed["retry_after_seconds"], 7)
            self.assertIsNone(failed["result"])
        finally:
            manager.close()

    def test_four_model_tasks_can_run_but_fifth_waits_for_a_slot(self):
        class BlockingProvider:
            def __init__(self):
                self.lock = threading.Lock()
                self.active = 0
                self.max_active = 0
                self.started_count = 0
                self.four_started = threading.Event()
                self.release = threading.Event()
            def reply_with_metadata(self, model, prompt, *, request_metadata=None, client_request_id=None):
                with self.lock:
                    self.active += 1
                    self.started_count += 1
                    self.max_active = max(self.max_active, self.active)
                    if self.active == 4:
                        self.four_started.set()
                self.release.wait(3)
                with self.lock:
                    self.active -= 1
                return "synthetic answer", model, 1, {
                    "response_id": "resp_concurrency", "request_id": "req_concurrency",
                    "http_status": 200, "retryable": False,
                }
        provider = BlockingProvider()
        manager = TaskManager(self.store, provider)
        try:
            tasks = [manager.submit("model-fixture", "model-fixture", "test-engineer", f"Task {i}")
                     for i in range(5)]
            self.assertTrue(provider.four_started.wait(2))
            with provider.lock:
                self.assertEqual(provider.started_count, 4)
                self.assertEqual(provider.max_active, 4)
            provider.release.set()
            completed = [self.wait_for_with(manager, task["task_id"], {"completed"}) for task in tasks]
            self.assertTrue(all(row["status"] == "completed" for row in completed))
            self.assertEqual(provider.max_active, 4)
        finally:
            provider.release.set()
            manager.close()

    def test_fifty_logical_task_slots_reject_the_fifty_first(self):
        tasks = [self.manager.submit("m", "m", "test-engineer", f"Await approval {i}",
                                     approval_required=True) for i in range(50)]
        self.assertEqual(len(tasks), 50)
        self.assertTrue(all(task["status"] == "awaiting_approval" for task in tasks))
        with self.assertRaisesRegex(RuntimeError, "TASK_CAPACITY_REACHED"):
            self.manager.submit("m", "m", "test-engineer", "Overflow", approval_required=True)
        self.assertEqual(self.provider.calls, 0)

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
