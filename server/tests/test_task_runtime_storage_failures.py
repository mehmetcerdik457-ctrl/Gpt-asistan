"""Injected SQLite/scheduling failures must end tasks without replaying providers."""
import json
import sqlite3
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch

from server import task_runtime as runtime


class FaultConnection(sqlite3.Connection):
    def execute(self, sql, parameters=(), /):
        statement = " ".join(sql.split())
        if statement.startswith("SELECT task_id,status,"):
            if self.faults.descriptor_failures:
                self.faults.descriptor_failures -= 1
                raise sqlite3.OperationalError("private descriptor read detail")
        elif statement.startswith("UPDATE owner_tasks SET status='running'"):
            self.faults.running_attempts += 1
            if self.faults.running_failures:
                self.faults.running_failures -= 1
                raise sqlite3.OperationalError("private initial running update detail")
        elif statement.startswith("UPDATE owner_tasks SET status='completed'"):
            self.faults.completed_attempts += 1
            if self.faults.completed_failures:
                self.faults.completed_failures -= 1
                raise sqlite3.OperationalError("private completion storage detail")
        elif (statement.startswith("UPDATE owner_tasks SET status=?")
              and parameters and parameters[0] in ("failed", "cancelled")):
            self.faults.terminal_attempts += 1
            if self.faults.terminal_failures:
                self.faults.terminal_failures -= 1
                raise sqlite3.OperationalError("private terminal storage detail")
        return super().execute(sql, parameters)


class FaultStore:
    def __init__(self, path):
        self.path = path
        self.arm()

    def arm(self, *, connects=0, descriptor=0, running=0, completed=0, terminal=0):
        self.connect_failures = connects
        self.descriptor_failures = descriptor
        self.running_failures = running
        self.completed_failures = completed
        self.terminal_failures = terminal
        self.connect_attempts = self.running_attempts = self.completed_attempts = self.terminal_attempts = 0

    def connect(self):
        self.connect_attempts += 1
        if self.connect_failures:
            self.connect_failures -= 1
            raise sqlite3.OperationalError("private initial connection detail")
        db = sqlite3.connect(self.path, timeout=1, factory=FaultConnection)
        db.faults = self
        return db

    def raw(self):
        """Observe durable state without triggering manager recovery or faults."""
        return sqlite3.connect(self.path, timeout=1)


class SyntheticFailure(Exception):
    code = "SYNTHETIC_PROVIDER_FAILED"
    provider_request_id = "req_failed_synthetic"
    provider_http_status = 503
    provider_error_code = "server_is_overloaded"
    retryable = True
    retry_after_seconds = 7


class SpyProvider:
    def __init__(self):
        self.calls = 0
        self.fail = False
        self.started = threading.Event()

    def reply(self, model, prompt):
        self.calls += 1
        self.started.set()
        if self.fail:
            raise SyntheticFailure("private provider detail")
        return "synthetic answer", model, 1

    def reply_with_metadata(self, model, prompt, **_):
        answer, actual, elapsed = self.reply(model, prompt)
        return answer, actual, elapsed, {
            "response_id": "resp_synthetic_success", "request_id": "req_synthetic_success",
            "http_status": 200, "provider_error_code": None, "retryable": False,
            "retry_after_seconds": None,
        }


class TaskRuntimeStorageFailureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = FaultStore(self.tmp.name + "/tasks.sqlite3")
        self.provider = SpyProvider()
        self.manager = runtime.TaskManager(self.store, self.provider)

    def tearDown(self):
        self.store.arm()
        self.manager.close()
        self.tmp.cleanup()

    def queued(self):
        task_id = uuid.uuid4().hex
        with self.store.raw() as db:
            db.execute(
                "INSERT INTO owner_tasks(task_id,status,created_at,updated_at,model,expert,"
                "request_sha256,client_request_id) VALUES(?, 'queued', 1, 1, ?, ?, ?, ?)",
                (task_id, "model-fixture", "test-engineer", "a" * 64, task_id))
        return task_id

    def run_task(self, task_id):
        self.manager._run(task_id, "model-fixture", "model-fixture", "test-engineer", "private prompt marker")

    def durable_status(self, task_id):
        with self.store.raw() as db:
            return db.execute("SELECT status,error_code FROM owner_tasks WHERE task_id=?", (task_id,)).fetchone()

    def assert_failed(self, task_id, code="TASK_STORAGE_FAILED"):
        row = self.manager.get(task_id)
        self.assertEqual((row["status"], row["error"]), ("failed", code))
        self.assertIsNone(row["result"])
        self.assertNotIn("private", json.dumps(row))
        return row

    def test_initial_connection_failure_records_failed_before_provider(self):
        task_id = self.queued()
        self.store.arm(connects=1)
        self.run_task(task_id)
        self.assertEqual(self.durable_status(task_id), ("failed", "TASK_STORAGE_FAILED"))
        self.assertEqual(self.store.connect_attempts, 2)
        self.assert_failed(task_id)
        self.assertEqual(self.provider.calls, 0)

    def test_initial_running_update_failure_records_failed_before_provider(self):
        task_id = self.queued()
        self.store.arm(running=1)
        self.run_task(task_id)
        self.assertEqual(self.store.running_attempts, 1)
        self.assert_failed(task_id)
        self.assertEqual(self.provider.calls, 0)

    def test_terminal_storage_retries_do_not_replay_provider(self):
        task_id = self.queued()
        self.provider.fail = True
        self.store.arm(terminal=2)
        self.run_task(task_id)
        self.assertEqual(self.store.terminal_attempts, 3)
        failed = self.assert_failed(task_id, "SYNTHETIC_PROVIDER_FAILED")
        self.assertEqual((failed["provider_request_id"], failed["provider_http_status"]),
                         ("req_failed_synthetic", 503))
        self.assertEqual(self.provider.calls, 1)

    def test_exhausted_initial_storage_retries_recover_on_get(self):
        task_id = self.queued()
        # One initial failure plus all three terminal persistence attempts.
        self.store.arm(connects=4)
        self.run_task(task_id)
        self.assertEqual(self.store.connect_attempts, 4)
        self.assertEqual(self.durable_status(task_id), ("queued", None))
        self.assert_failed(task_id)
        self.assertEqual(self.provider.calls, 0)

    def test_exhausted_terminal_writes_recover_on_get_without_provider_replay(self):
        task_id = self.queued()
        self.provider.fail = True
        self.store.arm(terminal=3)
        self.run_task(task_id)
        self.assertEqual(self.store.terminal_attempts, 3)
        self.assertEqual(self.durable_status(task_id), ("running", None))
        failed = self.assert_failed(task_id, "SYNTHETIC_PROVIDER_FAILED")
        self.assertEqual((failed["provider_request_id"], failed["provider_http_status"]),
                         ("req_failed_synthetic", 503))
        self.assertEqual(failed["provider_error_code"], "server_is_overloaded")
        self.assertTrue(failed["retryable"])
        self.assertEqual(failed["retry_after_seconds"], 7)
        self.assertEqual(self.provider.calls, 1)

    def test_completion_storage_failures_preserve_provider_correlation_without_replay(self):
        for terminal_failures in (1, 3):
            with self.subTest(terminal_failures=terminal_failures):
                task_id = self.queued()
                self.provider.calls = 0
                self.store.arm(completed=1, terminal=terminal_failures)
                self.run_task(task_id)
                self.assertEqual(self.store.completed_attempts, 1)
                if terminal_failures == 3:
                    self.assertEqual(self.durable_status(task_id), ("running", None))
                failed = self.assert_failed(task_id, "TASK_RESULT_STORAGE_FAILED")
                self.assertEqual((failed["response_id"], failed["provider_request_id"],
                                  failed["provider_http_status"]),
                                 ("resp_synthetic_success", "req_synthetic_success", 200))
                self.assertEqual(self.provider.calls, 1)

    def test_submit_recovers_pending_terminal_state_before_capacity_check(self):
        task_id = self.queued()
        self.store.arm(connects=4)
        self.run_task(task_id)
        self.assertEqual(self.durable_status(task_id), ("queued", None))
        with patch.object(runtime, "MAX_ACTIVE_TASKS", 1):
            next_task = self.manager.submit("model-fixture", "model-fixture", "test-engineer",
                                            "next synthetic task", approval_required=True)
        self.assertEqual(next_task["status"], "awaiting_approval")
        self.assertEqual(self.durable_status(task_id), ("failed", "TASK_STORAGE_FAILED"))
        self.assertEqual(self.provider.calls, 0)

    def test_pending_failure_cannot_overwrite_cancelled_or_restarted_terminal(self):
        for status, error in (("cancelled", "TASK_CANCELLED"), ("failed", "PROCESS_RESTARTED")):
            with self.subTest(status=status):
                task_id = self.queued()
                self.store.arm(connects=4)
                self.run_task(task_id)
                with self.store.raw() as db:
                    db.execute("UPDATE owner_tasks SET status=?,error_code=? WHERE task_id=?",
                               (status, error, task_id))
                row = self.manager.get(task_id)
                self.assertEqual((row["status"], row["error"]), (status, error))
        self.assertEqual(self.provider.calls, 0)

    def test_pool_scheduling_failure_is_terminal_and_releases_capacity(self):
        with patch.object(runtime, "MAX_ACTIVE_TASKS", 1):
            with patch.object(self.manager.pool, "submit", side_effect=RuntimeError("private scheduling detail")):
                task = self.manager.submit("model-fixture", "model-fixture", "test-engineer", "private prompt marker")
            self.assertEqual((task["status"], task["error"]), ("failed", "TASK_SCHEDULING_FAILED"))
            self.assertNotIn("private", json.dumps(task))
            next_task = self.manager.submit("model-fixture", "model-fixture", "test-engineer",
                                            "next synthetic task", approval_required=True)
        self.assertEqual(next_task["status"], "awaiting_approval")
        self.assertEqual(self.provider.calls, 0)

    def test_submit_enqueued_then_raised_cannot_dispatch_provider(self):
        real_submit = self.manager.pool.submit
        callback_entered = threading.Event()
        futures = []
        def enqueue_then_raise(callback, *args, **kwargs):
            def entered_callback():
                callback_entered.set()
                return callback(*args, **kwargs)
            future = real_submit(entered_callback)
            futures.append(future)
            self.assertTrue(callback_entered.wait(1))
            # On an ungated implementation let the provider finish before the
            # synthetic submit failure, making its forbidden dispatch observable.
            if self.provider.started.wait(0.1):
                future.result(timeout=1)
            raise RuntimeError("private failure after work item was enqueued")
        with patch.object(runtime, "MAX_ACTIVE_TASKS", 1):
            with patch.object(self.manager.pool, "submit", side_effect=enqueue_then_raise):
                task = self.manager.submit("model-fixture", "model-fixture", "test-engineer", "synthetic task")
            self.assertEqual((task["status"], task["error"]), ("failed", "TASK_SCHEDULING_FAILED"))
            self.assertIsNone(futures[0].result(timeout=1))
            next_task = self.manager.submit("model-fixture", "model-fixture", "test-engineer",
                                            "next synthetic task", approval_required=True)
        self.assertEqual(next_task["status"], "awaiting_approval")
        self.assertEqual(self.provider.calls, 0)

    def test_failed_accepted_descriptor_read_rolls_back_before_scheduling(self):
        self.store.arm(descriptor=1)
        with patch.object(self.manager.pool, "submit") as schedule:
            with self.assertRaises(sqlite3.OperationalError):
                self.manager.submit("model-fixture", "model-fixture", "test-engineer", "synthetic task")
        schedule.assert_not_called()
        with self.store.raw() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM owner_tasks").fetchone()[0], 0)
        self.assertEqual(self.provider.calls, 0)

    def test_successful_submit_returns_task_id_without_postdispatch_get(self):
        with patch.object(self.manager, "get", side_effect=sqlite3.OperationalError("private later read detail")):
            accepted = self.manager.submit("model-fixture", "model-fixture", "test-engineer", "synthetic task")
        self.assertRegex(accepted["task_id"], r"^[a-f0-9]{32}$")
        self.assertEqual(accepted["status"], "queued")
        self.manager.pool.shutdown(wait=True)
        completed = self.manager.get(accepted["task_id"])
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(self.provider.calls, 1)


if __name__ == "__main__":
    unittest.main()
