"""Real SQLite/HTTP submissions recover one durable task without another POST."""
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from server import gateway as g, task_runtime as runtime
from server.tests import test_gateway as http_fixture
from server.tests import test_task_runtime as task_fixture
from server.tests import test_task_runtime_storage_failures as faults


class TaskSubmissionIdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = faults.FaultStore(self.tmp.name + "/tasks.sqlite3")
        self.provider = task_fixture.FakeProvider()
        self.manager = runtime.TaskManager(self.store, self.provider)
        self.key = uuid.uuid4().hex

    def tearDown(self):
        self.store.arm()
        self.provider.release.set()
        self.manager.close()
        self.tmp.cleanup()

    def submit(self, key=None, *, model="model-fixture", expert="test-engineer", prompt="private task input",
               approval=False, manager=None):
        return (manager or self.manager).submit(
            model, model, expert, prompt, approval_required=approval,
            idempotency_key=key or self.key)

    def wait_terminal(self, task_id):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            result = self.manager.get(task_id)
            if result["status"] in ("completed", "failed", "cancelled"):
                return result
            time.sleep(0.005)
        self.fail("task did not settle")

    def test_concurrent_misses_from_two_managers_schedule_only_one_provider_call(self):
        other = runtime.TaskManager(self.store, self.provider)
        self.provider.block = True
        barrier = threading.Barrier(8)
        def submit(index):
            barrier.wait(2)
            return self.submit(manager=other if index % 2 else self.manager)
        try:
            with ThreadPoolExecutor(max_workers=8) as pool:
                accepted = list(pool.map(submit, range(8)))
            self.assertEqual({row["task_id"] for row in accepted}, {self.key})
            self.assertTrue(self.provider.started.wait(1))
            self.assertEqual(self.provider.calls, 1)
            self.provider.release.set()
            completed = self.wait_terminal(self.key)
            self.assertEqual(completed["status"], "completed")
            self.assertEqual(self.submit(), completed)
            self.assertEqual(self.provider.calls, 1)
            with self.store.raw() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM owner_tasks").fetchone()[0], 1)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM task_submissions").fetchone()[0], 1)
        finally:
            self.provider.release.set()
            other.close()

    def test_same_key_cannot_change_input_model_expert_or_approval(self):
        accepted = self.submit(approval=True)
        changes = ({"prompt": "different input", "approval": True},
                   {"model": "different-model", "approval": True},
                   {"expert": "security-auditor", "approval": True},
                   {"approval": False})
        for change in changes:
            with self.subTest(change=change), self.assertRaisesRegex(
                    runtime.TaskIdempotencyConflict, "TASK_IDEMPOTENCY_KEY_CONFLICT"):
                self.submit(**change)
        self.assertEqual(self.submit(approval=True), accepted)
        self.assertEqual(self.provider.calls, 0)

    def test_new_logical_key_with_same_content_is_a_distinct_intent(self):
        first = self.submit()
        second = self.submit(uuid.uuid4().hex)
        self.assertNotEqual(first["task_id"], second["task_id"])
        self.assertEqual(self.wait_terminal(first["task_id"])["status"], "completed")
        self.assertEqual(self.wait_terminal(second["task_id"])["status"], "completed")
        self.assertEqual(self.provider.calls, 2)

    def test_restart_in_a_new_process_recovers_failure_without_resubmission(self):
        accepted = self.submit(approval=True)
        with self.store.raw() as db:
            db.execute("UPDATE owner_tasks SET status='running' WHERE task_id=?", (self.key,))
        self.manager.close()
        program = '''
import json, sqlite3, sys
from server.task_runtime import TaskManager
class Store:
    def connect(self): return sqlite3.connect(sys.argv[1], timeout=3)
class NeverProvider:
    def reply(self, *_): raise AssertionError("duplicate provider dispatch")
m = TaskManager(Store(), NeverProvider())
try:
    task = m.submit("model-fixture", "model-fixture", "test-engineer", "private task input",
                    approval_required=True, idempotency_key=sys.argv[2])
    print(json.dumps(task))
finally:
    m.close()
'''
        result = subprocess.run([sys.executable, "-c", program, str(self.store.path), self.key],
                                cwd=Path(__file__).resolve().parents[2], capture_output=True,
                                text=True, timeout=5, check=True)
        recovered = json.loads(result.stdout)
        self.assertEqual((recovered["task_id"], recovered["status"], recovered["error"]),
                         (accepted["task_id"], "failed", "PROCESS_RESTARTED"))
        self.assertEqual(self.provider.calls, 0)

    def test_descriptor_read_failure_rolls_back_task_and_key_before_dispatch(self):
        self.store.arm(descriptor=1)
        with self.assertRaises(sqlite3.OperationalError):
            self.submit()
        with self.store.raw() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM owner_tasks").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM task_submissions").fetchone()[0], 0)
        self.assertEqual(self.provider.calls, 0)
        accepted = self.submit()
        self.assertEqual(self.wait_terminal(accepted["task_id"])["status"], "completed")
        self.assertEqual(self.provider.calls, 1)

    def test_scheduling_rejection_remains_retrievable_without_another_schedule(self):
        with patch.object(self.manager.pool, "submit", side_effect=RuntimeError("synthetic rejection")) as schedule:
            failed = self.submit()
            self.assertEqual((failed["status"], failed["error"]), ("failed", "TASK_SCHEDULING_FAILED"))
            self.assertEqual(self.submit(), failed)
            self.assertEqual(schedule.call_count, 1)
        self.assertEqual(self.provider.calls, 0)

    def test_uncertain_provider_outcome_is_never_repeated_for_same_key(self):
        with patch.object(self.provider, "reply_with_metadata", side_effect=TimeoutError("uncertain POST")) as post:
            self.submit()
            failed = self.wait_terminal(self.key)
            for _ in range(3):
                self.assertEqual(self.submit(), failed)
            self.assertEqual(post.call_count, 1)
        self.assertEqual(failed["status"], "failed")
        self.assertIsNone(failed["result"])

    def test_approval_and_cancelled_submissions_are_returned_without_execution(self):
        for transition, expected in ((self.manager.approve, "approved_not_executed"),
                                     (self.manager.cancel, "cancelled")):
            with self.subTest(expected=expected):
                key = uuid.uuid4().hex
                accepted = self.submit(key, approval=True)
                final = transition(accepted["task_id"])
                self.assertEqual(final["status"], expected)
                self.assertEqual(self.submit(key, approval=True), final)
        self.assertEqual(self.provider.calls, 0)

    def test_legacy_uuid_collision_cannot_adopt_or_replace_the_old_task(self):
        with patch.object(runtime.uuid, "uuid4", return_value=uuid.UUID(self.key)):
            legacy = self.manager.submit("model-fixture", "model-fixture", "test-engineer",
                                         "legacy input", approval_required=True)
        with self.assertRaises(runtime.TaskIdempotencyConflict):
            self.submit(approval=True)
        self.assertEqual(self.manager.get(self.key), legacy)
        with self.store.raw() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM task_submissions").fetchone()[0], 0)
        self.assertEqual(self.provider.calls, 0)

    def test_missing_reserved_task_fails_closed_instead_of_recreating_paid_work(self):
        self.submit(approval=True)
        with self.store.raw() as db:
            db.execute("DELETE FROM owner_tasks WHERE task_id=?", (self.key,))
        with self.assertRaisesRegex(runtime.TaskIdempotencyUnavailable, "TASK_IDEMPOTENCY_RECORD_INVALID"):
            self.submit(approval=True)
        self.assertEqual(self.provider.calls, 0)
        with self.store.raw() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM owner_tasks").fetchone()[0], 0)
            mapping = db.execute("SELECT key_sha256,task_id FROM task_submissions").fetchone()
            self.assertEqual(mapping, (hashlib.sha256(self.key.encode()).hexdigest(), self.key))

    def test_alias_validation_and_unkeyed_backwards_compatibility(self):
        for invalid in ("", "a" * 31, "A" * 32, 4, False, "x" * 128):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "TASK_IDEMPOTENCY_KEY_INVALID"):
                runtime.submission_key(invalid)
        with self.assertRaises(ValueError):
            runtime.submission_key(self.key, uuid.uuid4().hex)
        self.assertEqual(runtime.submission_key(None, self.key), self.key)
        first = self.manager.submit("m", "m", "test-engineer", "legacy", approval_required=True)
        second = self.manager.submit("m", "m", "test-engineer", "legacy", approval_required=True)
        self.assertNotEqual(first["task_id"], second["task_id"])
        self.assertEqual(self.provider.calls, 0)


class TaskSubmissionHttpTests(unittest.TestCase):
    """Reuse the existing real HTTP/P-256 fixture without inheriting its tests."""
    def setUp(self):
        self.fixture = http_fixture.GatewayHttpTests()
        self.fixture.setUp()
        self.fixture.verify_model()
        self.key = uuid.uuid4().hex
        self.payload = {"input": "synthetic task", "model": self.fixture.provider.actual,
                        "expert": "test-engineer", "tools": [],
                        "client_request_id": self.key, "idempotency_key": self.key}

    def tearDown(self):
        self.fixture.tearDown()

    def test_signed_retry_after_lost_acceptance_and_expired_registry_does_not_repeat_post(self):
        code, accepted = self.fixture.post("tasks", self.payload)
        self.assertEqual(code, 200)
        self.assertEqual(accepted["task_id"], self.key)
        self.assertEqual(accepted["client_request_id"], self.key)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            code, completed = self.fixture.post("tasks/status", {"task_id": self.key})
            if completed["status"] == "completed":
                break
            time.sleep(0.005)
        self.assertEqual(completed["status"], "completed")
        self.fixture.gateway.models.clear()
        self.fixture.gateway.calls.extend([time.time()] * 10)
        calls = list(self.fixture.provider.calls)
        for _ in range(3):
            code, recovered = self.fixture.post("tasks", self.payload)
            self.assertEqual((code, recovered), (200, completed))
        self.assertEqual(self.fixture.provider.calls, calls)
        self.assertEqual(len([call for call in calls if not call[2]]), 1)
        code, denial = self.fixture.post("tasks", {**self.payload, "requires_approval": True})
        self.assertEqual((code, denial["error"]), (409, "TASK_IDEMPOTENCY_KEY_CONFLICT"))
        code, denial = self.fixture.post("tasks", self.payload, owner="different-owner")
        self.assertEqual(code, 403)
        self.assertNotIn("task_id", denial)
        self.assertEqual(self.fixture.provider.calls, calls)

    def test_invalid_key_alias_tools_and_unknown_fields_cannot_dispatch_provider(self):
        calls = list(self.fixture.provider.calls)
        invalid = (({"idempotency_key": None}, "TASK_IDEMPOTENCY_KEY_INVALID"),
                   ({"client_request_id": uuid.uuid4().hex}, "TASK_IDEMPOTENCY_KEY_INVALID"),
                   ({"idempotency_key": "A" * 32}, "TASK_IDEMPOTENCY_KEY_INVALID"),
                   ({"unexpected": True}, "TASK_FIELDS_DENIED"))
        for change, error in invalid:
            with self.subTest(change=change):
                code, denial = self.fixture.post("tasks", {**self.payload, **change})
                self.assertEqual((code, denial["error"]), (400, error))
        code, denial = self.fixture.post("tasks", {**self.payload, "tools": ["shell"]})
        self.assertEqual((code, denial["error"]), (403, "TASK_TOOL_CAPABILITY_DENIED"))
        self.assertEqual(self.fixture.provider.calls, calls)


if __name__ == "__main__":
    unittest.main()
