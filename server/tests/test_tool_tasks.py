"""Local approval contracts with temporary SQLite and real signed HTTP requests.

All identities and content are synthetic. No model or external service is used.
"""
import base64
import copy
import hashlib
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from server import gateway as g, kral_memory, owner_auth_v1 as auth
from server.tool_tasks import ToolDenied, ToolTasks


ACTOR = {"owner_id": "owner-fixture", "device_id": "a" * 64,
         "owner_key_sha256": "b" * 64}


def proposal(text="Synthetic approval-only memory"):
    return {"tool": "memory.save", "arguments": {"text": text}, "scope": "local.memory"}


def reference(task):
    return {"tool_task_id": task["tool_task_id"], "request_sha256": task["request_sha256"]}


def approval(task):
    return {**reference(task), "tool": task["tool"],
            "arguments": copy.deepcopy(task["arguments"]), "scope": task["scope"]}


class ToolPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = g.Store(str(Path(self.tmp.name) / "data.sqlite3"))
        self.now = [1793700000]
        self.manager = ToolTasks(self.store, clock=lambda: self.now[0])

    def tearDown(self):
        self.tmp.cleanup()

    def memory_rows(self):
        with self.store.connect() as db:
            return db.execute("SELECT id,text FROM memory ORDER BY id").fetchall()

    def assert_denied(self, code, operation, *args):
        with self.assertRaises(ToolDenied) as caught:
            operation(*args)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_pending_action_is_exact_and_does_not_write_memory(self):
        body = proposal()
        task = self.manager.submit(body, ACTOR)
        self.assertEqual(task["status"], "awaiting_approval")
        self.assertEqual(task["approval_class"], "owner_approval")
        self.assertEqual((task["tool"], task["arguments"], task["scope"]),
                         (body["tool"], body["arguments"], body["scope"]))
        self.assertEqual(task["actor"], ACTOR)
        self.assertEqual(task["expires_at"] - task["created_at"], 300)
        self.assertEqual((task["tools_executed"], task["external_actions"]), (0, 0))
        self.assertIsNone(task["result"])
        self.assertEqual(self.memory_rows(), [])
        self.assertEqual([item["event"] for item in task["audit"]], ["proposed"])
        self.assertNotIn(body["arguments"]["text"], json.dumps(task["audit"]))
        self.assertEqual(self.manager.get(reference(task), ACTOR)["request_sha256"],
                         task["request_sha256"])

    def test_unknown_tools_invalid_arguments_and_scopes_are_rejected(self):
        cases = [
            ({"tool": "shell", "arguments": {}, "scope": "local.status"}, "TOOL_CAPABILITY_DENIED"),
            ({"tool": "status", "arguments": {"command": "id"}, "scope": "local.status"}, "TOOL_ARGUMENTS_INVALID"),
            ({"tool": "status", "arguments": {}, "scope": "remote.admin"}, "TOOL_SCOPE_DENIED"),
            (proposal("   "), "TOOL_ARGUMENTS_INVALID"),
            (proposal("x" * 8001), "TOOL_ARGUMENTS_INVALID"),
            ({**proposal(), "arguments": {"text": "fixture", "embedding": []}}, "TOOL_ARGUMENTS_INVALID"),
            ({**proposal(), "approval_class": "read_only"}, "TOOL_FIELDS_INVALID"),
            ({**proposal(), "actor": ACTOR}, "TOOL_FIELDS_INVALID"),
        ]
        for body, code in cases:
            with self.subTest(code=code, tool=body["tool"]):
                self.assert_denied(code, self.manager.submit, body, ACTOR)
        self.assertEqual(self.memory_rows(), [])

    def test_approval_binds_tool_arguments_scope_and_digest(self):
        task = self.manager.submit(proposal(), ACTOR)
        for field, value in (("tool", "status"), ("arguments", {"text": "altered"}),
                             ("scope", "local.status"), ("request_sha256", "0" * 64)):
            with self.subTest(field=field):
                changed = {**approval(task), field: value}
                self.assert_denied("TOOL_APPROVAL_MISMATCH", self.manager.approve, changed, ACTOR)
        self.assertEqual(self.manager.get(reference(task), ACTOR)["status"], "awaiting_approval")
        self.assertEqual(self.memory_rows(), [])

    def test_actor_owner_device_and_key_rebinding_are_denied(self):
        task = self.manager.submit(proposal(), ACTOR)
        for field, value in (("owner_id", "different-owner"), ("device_id", "c" * 64),
                             ("owner_key_sha256", "d" * 64)):
            with self.subTest(field=field):
                other = {**ACTOR, field: value}
                self.assert_denied("TOOL_ACTOR_DENIED", self.manager.approve, approval(task), other)
                self.assert_denied("TOOL_ACTOR_DENIED", self.manager.get, reference(task), other)
        self.assert_denied("TOOL_ACTOR_DENIED", self.manager.submit, proposal(), None)
        self.assertEqual(self.memory_rows(), [])

    def test_expired_or_cancelled_actions_cannot_execute(self):
        expired = self.manager.submit(proposal("Expiry fixture"), ACTOR)
        cancelled = self.manager.submit(proposal("Cancellation fixture"), ACTOR)
        self.assertEqual(self.manager.cancel(reference(cancelled), ACTOR)["status"], "cancelled")
        self.assert_denied("TOOL_TASK_NOT_PENDING", self.manager.approve, approval(cancelled), ACTOR)
        self.now[0] = expired["expires_at"]
        self.assert_denied("TOOL_TASK_EXPIRED", self.manager.approve, approval(expired), ACTOR)
        current = self.manager.get(reference(expired), ACTOR)
        self.assertEqual(current["status"], "expired")
        self.assertEqual(current["audit"][-1]["event"], "expired")
        self.assertEqual(self.memory_rows(), [])

    def test_restart_preserves_pending_and_completed_single_use_evidence(self):
        task = self.manager.submit(proposal(), ACTOR)
        restarted = ToolTasks(self.store, clock=lambda: self.now[0])
        completed = restarted.approve(approval(task), ACTOR)
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["approved_by"], ACTOR)
        self.assertEqual((completed["tools_executed"], completed["external_actions"]), (1, 0))
        self.assertEqual(self.memory_rows(), [(completed["result"]["id"], task["arguments"]["text"])])
        self.assertEqual([event["event"] for event in completed["audit"]],
                         ["proposed", "approved", "completed"])
        after_completion = ToolTasks(self.store, clock=lambda: self.now[0])
        self.assert_denied("TOOL_TASK_NOT_PENDING", after_completion.approve, approval(task), ACTOR)
        self.assertEqual(len(self.memory_rows()), 1)

    def test_concurrent_approvals_execute_exactly_once(self):
        task = self.manager.submit(proposal(), ACTOR)
        barrier = threading.Barrier(2)

        def execute():
            barrier.wait(timeout=3)
            try:
                return self.manager.approve(approval(task), ACTOR)["status"]
            except ToolDenied as error:
                return error.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: execute(), range(2)))
        self.assertCountEqual(outcomes, ["completed", "TOOL_TASK_NOT_PENDING"])
        self.assertEqual(len(self.memory_rows()), 1)
        current = self.manager.get(reference(task), ACTOR)
        self.assertEqual([event["event"] for event in current["audit"]].count("completed"), 1)

    def test_handler_failure_rolls_back_memory_and_approval_evidence_together(self):
        task = self.manager.submit(proposal(), ACTOR)
        original = kral_memory.remember

        def failing_handler(db, text):
            original(db, text)
            raise RuntimeError("synthetic handler failure")

        with patch("server.tool_tasks.kral_memory.remember", side_effect=failing_handler):
            with self.assertRaises((RuntimeError, ToolDenied)):
                self.manager.approve(approval(task), ACTOR)
        self.assertEqual(self.memory_rows(), [])
        current = self.manager.get(reference(task), ACTOR)
        self.assertEqual(current["status"], "awaiting_approval")
        self.assertIsNone(current["approved_at"])
        self.assertEqual([event["event"] for event in current["audit"]], ["proposed"])
        self.assertEqual(self.manager.approve(approval(task), ACTOR)["status"], "completed")
        self.assertEqual(len(self.memory_rows()), 1)

    def test_pending_capacity_is_bounded_and_expiry_releases_capacity(self):
        for number in range(50):
            self.manager.submit(proposal(f"Synthetic pending action {number}"), ACTOR)
        error = self.assert_denied("TOOL_TASK_CAPACITY_REACHED", self.manager.submit, proposal(), ACTOR)
        self.assertEqual(error.status, 429)
        self.now[0] += 300
        self.assertEqual(self.manager.submit(proposal(), ACTOR)["status"], "awaiting_approval")
        self.assertEqual(self.memory_rows(), [])


class NoProvider:
    name = "never-call"

    def __init__(self):
        self.calls = 0

    def reply(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("provider must not be called by local tool tasks")


class ToolHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.owner = ec.generate_private_key(ec.SECP256R1())
        self.device = ec.generate_private_key(ec.SECP256R1())
        self.owner_der = self.der(self.owner)
        self.device_id = hashlib.sha256(self.der(self.device)).hexdigest()
        self.env = patch.dict(os.environ, {
            "OMEGA_OWNER_ID": "owner-fixture", "OMEGA_DEVICE_ID": self.device_id,
            "OMEGA_OWNER_PUBLIC_DER_B64": self.b64(self.owner_der),
            "OMEGA_DEVICE_PUBLIC_DER_B64": self.b64(self.der(self.device)),
            "OMEGA_NONCE_DB": str(Path(self.tmp.name) / "nonces.sqlite3"),
        })
        self.env.start()
        self.provider = NoProvider()
        self.gateway = g.Gateway(g.Store(str(Path(self.tmp.name) / "data.sqlite3")), self.provider)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), g.handler_for(self.gateway))
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=3)
        self.gateway.tasks.close()
        self.assertEqual(self.provider.calls, 0)
        self.env.stop()
        self.tmp.cleanup()

    @staticmethod
    def b64(value):
        return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

    @staticmethod
    def der(key):
        return key.public_key().public_bytes(serialization.Encoding.DER,
                                            serialization.PublicFormat.SubjectPublicKeyInfo)

    def signed_headers(self, path, raw):
        timestamp = str(int(time.time()))
        nonce = uuid.uuid4().hex
        message = auth.canonical("POST", path, raw, timestamp, nonce, "owner-fixture", self.device_id)
        return {"Content-Type": "application/json", "X-Omega-Owner-Id": "owner-fixture",
                "X-Omega-Device-Id": self.device_id, "X-Omega-Timestamp": timestamp,
                "X-Omega-Nonce": nonce,
                "X-Omega-Owner-Proof": self.b64(self.owner.sign(message, ec.ECDSA(hashes.SHA256()))),
                "X-Omega-Device-Proof": self.b64(self.device.sign(message, ec.ECDSA(hashes.SHA256())))}

    def post(self, route, body, headers=None):
        path = g.PREFIX + route
        raw = g.json_bytes(body)
        headers = self.signed_headers(path, raw) if headers is None else headers
        request = urllib.request.Request(self.url + path, data=raw, method="POST", headers=headers)
        try:
            response = self.opener.open(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def pending(self):
        status, task = self.post("tool-tasks", proposal())
        self.assertEqual(status, 200)
        self.assertEqual(task["status"], "awaiting_approval")
        self.assertEqual(self.gateway.store.recall(""), [])
        return task

    def test_signed_status_read_runs_with_backend_derived_actor(self):
        status, task = self.post("tool-tasks", {"tool": "status", "arguments": {}, "scope": "local.status"})
        self.assertEqual(status, 200)
        self.assertEqual(task["contract"], g.CONTRACT)
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["approval_class"], "read_only")
        self.assertFalse(task["result"]["external_execution"])
        self.assertEqual(task["actor"], {"owner_id": "owner-fixture", "device_id": self.device_id,
                                        "owner_key_sha256": hashlib.sha256(self.owner_der).hexdigest()})
        self.assertEqual((task["tools_executed"], task["external_actions"]), (1, 0))

    def test_signed_approval_executes_only_the_exact_pending_memory_write(self):
        task = self.pending()
        status, completed = self.post("tool-tasks/approve", approval(task))
        self.assertEqual(status, 200)
        self.assertEqual(completed["status"], "completed")
        rows = self.gateway.store.recall("")
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["id"], rows[0]["text"]),
                         (completed["result"]["id"], task["arguments"]["text"]))
        status, current = self.post("tool-tasks/status", reference(task))
        self.assertEqual(status, 200)
        self.assertEqual(current["approved_by"], task["actor"])
        self.assertEqual([event["event"] for event in current["audit"]],
                         ["proposed", "approved", "completed"])

    def test_unsigned_and_tampered_signed_approvals_never_write(self):
        task = self.pending()
        body = approval(task)
        status, _ = self.post("tool-tasks/approve", body, headers={"Content-Type": "application/json"})
        self.assertEqual(status, 403)
        headers = self.signed_headers(g.PREFIX + "tool-tasks/approve", g.json_bytes(body))
        changed = {**body, "arguments": {"text": "tampered after signing"}}
        status, _ = self.post("tool-tasks/approve", changed, headers=headers)
        self.assertEqual(status, 403)
        self.assertEqual(self.gateway.store.recall(""), [])

    def test_replayed_or_duplicate_approval_never_repeats_write(self):
        task = self.pending()
        body = approval(task)
        headers = self.signed_headers(g.PREFIX + "tool-tasks/approve", g.json_bytes(body))
        self.assertEqual(self.post("tool-tasks/approve", body, headers=headers)[0], 200)
        self.assertEqual(self.post("tool-tasks/approve", body, headers=headers)[0], 403)
        status, denied = self.post("tool-tasks/approve", body)
        self.assertEqual((status, denied["error"]), (409, "TOOL_TASK_NOT_PENDING"))
        self.assertEqual(len(self.gateway.store.recall("")), 1)

    def test_client_cannot_override_actor_policy_or_tool_scope(self):
        for body, expected in (
            ({**proposal(), "actor": ACTOR}, 400),
            ({**proposal(), "approval_class": "read_only"}, 400),
            ({**proposal(), "tool": "github.merge"}, 403),
            ({**proposal(), "scope": "remote.admin"}, 403),
        ):
            with self.subTest(body=body):
                self.assertEqual(self.post("tool-tasks", body)[0], expected)
        self.assertEqual(self.gateway.store.recall(""), [])

    def test_signed_cancel_prevents_later_approval(self):
        task = self.pending()
        status, cancelled = self.post("tool-tasks/cancel", reference(task))
        self.assertEqual(status, 200)
        self.assertEqual(cancelled["status"], "cancelled")
        status, denied = self.post("tool-tasks/approve", approval(task))
        self.assertEqual((status, denied["error"]), (409, "TOOL_TASK_NOT_PENDING"))
        self.assertEqual(self.gateway.store.recall(""), [])


if __name__ == "__main__":
    unittest.main()
