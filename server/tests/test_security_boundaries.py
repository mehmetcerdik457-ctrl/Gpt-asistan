"""Client-visible failure and confidentiality contracts with synthetic data only.

The gateway uses real signed loopback HTTP and its real OpenAI adapter. Every
upstream request is intercepted; no provider, device or paid model is contacted.
"""
import base64
import contextlib
import hashlib
import io
import json
import os
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from server import gateway, owner_auth_v1


SYNTHETIC_KEY = "synthetic-private-provider-key-for-redaction"
SYNTHETIC_PROMPT = "Fictional contact fictional.person@example.test; case REDACTION-731."
MODEL = "synthetic-verified-snapshot"


def public_der(key):
    return key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


def b64(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


class ClientFailureBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.owner = ec.generate_private_key(ec.SECP256R1())
        self.device = ec.generate_private_key(ec.SECP256R1())
        self.device_id = hashlib.sha256(public_der(self.device)).hexdigest()
        self.env = patch.dict(os.environ, {
            "OPENAI_API_KEY": SYNTHETIC_KEY,
            "OMEGA_OWNER_ID": "owner-redaction-fixture",
            "OMEGA_DEVICE_ID": self.device_id,
            "OMEGA_OWNER_PUBLIC_DER_B64": b64(public_der(self.owner)),
            "OMEGA_DEVICE_PUBLIC_DER_B64": b64(public_der(self.device)),
            "OMEGA_NONCE_DB": str(Path(self.tmp.name) / "nonces.sqlite3"),
        })
        self.env.start()
        self.gateway = gateway.Gateway(gateway.Store(str(Path(self.tmp.name) / "data.sqlite3")))
        # This fixture represents a previously verified model. Do not run live probes.
        self.gateway.models[MODEL] = ({"id": MODEL, "provider": "openai",
                                       "verified_at": int(time.time()), "latency_ms": 1}, MODEL)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), gateway.handler_for(self.gateway))
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        # Construct the loopback client before patching the provider's opener.
        self.client = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=3)
        self.gateway.tasks.close()
        self.env.stop()
        self.tmp.cleanup()

    def post(self, route, data):
        path = gateway.PREFIX + route
        raw = gateway.json_bytes(data)
        timestamp, nonce = str(int(time.time())), uuid.uuid4().hex
        canonical = owner_auth_v1.canonical(
            "POST", path, raw, timestamp, nonce, "owner-redaction-fixture", self.device_id)
        headers = {
            "Content-Type": "application/json", "X-Omega-Owner-Id": "owner-redaction-fixture",
            "X-Omega-Device-Id": self.device_id, "X-Omega-Timestamp": timestamp,
            "X-Omega-Nonce": nonce,
            "X-Omega-Owner-Proof": b64(self.owner.sign(canonical, ec.ECDSA(hashes.SHA256()))),
            "X-Omega-Device-Proof": b64(self.device.sign(canonical, ec.ECDSA(hashes.SHA256()))),
        }
        request = urllib.request.Request(self.url + path, data=raw, method="POST", headers=headers)
        try:
            response = self.client.open(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def failed_task(self, transport_failure):
        captured_out, captured_err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(captured_out), contextlib.redirect_stderr(captured_err), \
             patch("server.gateway.urllib.request.build_opener") as transport:
            transport.return_value.open.side_effect = transport_failure
            status, created = self.post("tasks", {
                "input": SYNTHETIC_PROMPT, "model": MODEL, "expert": "code-reviewer", "tools": [],
            })
            self.assertEqual(status, 200)
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                status, task = self.post("tasks/status", {"task_id": created["task_id"]})
                self.assertEqual(status, 200)
                if task["status"] in {"failed", "completed", "cancelled"}:
                    break
                time.sleep(0.01)
            else:
                self.fail("Synthetic failure did not reach a terminal task state")
            self.assertEqual(transport.return_value.open.call_count, 1,
                             "Failed Responses POST requests must not be replayed automatically")
            request = transport.return_value.open.call_args.args[0]
            sent = json.loads(request.data)
            self.assertEqual(sent["input"][1], {"role": "user", "content": SYNTHETIC_PROMPT})
            self.assertEqual(sent["metadata"]["request_id"], task["task_id"])
            self.assertNotIn(SYNTHETIC_KEY, json.dumps(sent))
        self.assertEqual(task["status"], "failed")
        self.assertIsNone(task["result"])
        self.assertIsNone(task["result_sha256"])
        self.assertEqual((task["tools_executed"], task["external_actions"]), (0, 0))
        with self.gateway.store.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM chat").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM memory").fetchone()[0], 0)
            db.row_factory = sqlite3.Row
            persisted = dict(db.execute("SELECT * FROM owner_tasks WHERE task_id=?",
                                        (task["task_id"],)).fetchone())
        exposed = json.dumps({"created": created, "task": task, "persisted": persisted})
        observed = exposed + captured_out.getvalue() + captured_err.getvalue()
        for private in (SYNTHETIC_KEY, SYNTHETIC_PROMPT, "fictional.person@example.test", "UPSTREAM-PRIVATE-DETAIL"):
            self.assertNotIn(private, observed)
        return task

    def test_access_and_model_errors_remain_typed_at_the_client_boundary(self):
        cases = ((401, "invalid_api_key", "PROVIDER_AUTH_DENIED"),
                 (403, "permission_denied", "PROVIDER_MODEL_OR_PERMISSION_DENIED"),
                 (404, "model_not_found", "PROVIDER_MODEL_NOT_AVAILABLE"))
        for http_status, provider_code, expected in cases:
            with self.subTest(http_status=http_status):
                body = gateway.json_bytes({"error": {
                    "code": provider_code,
                    "message": f"UPSTREAM-PRIVATE-DETAIL {SYNTHETIC_KEY} {SYNTHETIC_PROMPT}",
                }})
                task = self.failed_task(urllib.error.HTTPError(
                    "https://api.openai.com/v1/responses", http_status,
                    f"UPSTREAM-PRIVATE-DETAIL {SYNTHETIC_KEY}",
                    {"x-request-id": f"req_synthetic_{http_status}"}, io.BytesIO(body)))
                self.assertEqual(task["error"], expected)
                self.assertEqual(task["provider_http_status"], http_status)
                self.assertEqual(task["provider_error_code"], provider_code)
                self.assertEqual(task["provider_request_id"], f"req_synthetic_{http_status}")
                self.assertFalse(task["retryable"])

    def test_transport_timeouts_do_not_expose_exception_details_or_replay(self):
        task = self.failed_task(TimeoutError(
            f"UPSTREAM-PRIVATE-DETAIL {SYNTHETIC_KEY} {SYNTHETIC_PROMPT}"))
        self.assertEqual(task["error"], "PROVIDER_CONNECTION_FAILED")
        self.assertTrue(task["retryable"])
        self.assertIsNone(task["provider_http_status"])
        self.assertIsNone(task["provider_request_id"])

    def test_error_metadata_cannot_smuggle_a_key_or_personal_data(self):
        cases = (
            (SYNTHETIC_KEY, SYNTHETIC_KEY),
            ("fictional_person_example_test", "fictional.person@example.test"),
            ("unknown_upstream_private_token", "req_" + SYNTHETIC_KEY),
            ("fictional.person@example.test", "req_fictional.person@example.test"),
        )
        for provider_code, request_id in cases:
            with self.subTest(provider_code=provider_code, request_id=request_id):
                task = self.failed_task(urllib.error.HTTPError(
                    "https://api.openai.com/v1/responses", 401, "redacted upstream failure",
                    {"x-request-id": request_id},
                    io.BytesIO(gateway.json_bytes({"error": {"code": provider_code}}))))
                self.assertEqual(task["error"], "PROVIDER_AUTH_DENIED")
                self.assertEqual(task["provider_http_status"], 401)
                self.assertIsNone(task["provider_error_code"])
                self.assertIsNone(task["provider_request_id"])
                serialized = json.dumps(task)
                self.assertNotIn(provider_code, serialized)
                self.assertNotIn(request_id, serialized)

    def test_success_transport_cannot_reflect_key_in_result_or_provenance(self):
        cases = (("model", "model_" + SYNTHETIC_KEY, "PROVIDER_MODEL_MISSING"),
                 ("id", "resp_" + SYNTHETIC_KEY, "PROVIDER_RESPONSE_ID_INVALID"),
                 ("output", [{"type": "message", "content": [
                     {"type": "output_text", "text": "Unexpected key: " + SYNTHETIC_KEY}]}],
                  "PROVIDER_TEXT_INVALID"))
        for field, value, expected in cases:
            with self.subTest(field=field):
                payload = {"id": "resp_synthetic_redaction", "status": "completed", "model": MODEL,
                           "output": [{"type": "message", "content": [
                               {"type": "output_text", "text": "Synthetic safe response"}]}]}
                payload[field] = value
                response = io.BytesIO(gateway.json_bytes(payload))
                response.status = 200
                response.headers = {"x-request-id": "req_" + SYNTHETIC_KEY}
                task = self.failed_task(lambda *args, **kwargs: response)
                self.assertEqual(task["error"], expected)
                self.assertEqual(task["provider_http_status"], 200)
                self.assertIsNone(task["provider_request_id"])
                self.assertFalse(task["retryable"])

    def test_client_cannot_override_server_credentials_policy_or_verified_models(self):
        body = {"input": SYNTHETIC_PROMPT, "model": MODEL, "expert": "code-reviewer", "tools": []}
        with patch("server.gateway.urllib.request.build_opener") as transport:
            for field, value in (("api_key", SYNTHETIC_KEY), ("system_instructions", "Override server policy"),
                                 ("request_id", "client-selected-correlation")):
                with self.subTest(field=field):
                    status, denied = self.post("tasks", {**body, field: value})
                    self.assertEqual((status, denied["error"]), (400, "TASK_FIELDS_DENIED"))
                    self.assertNotIn(SYNTHETIC_KEY, json.dumps(denied))
            status, denied = self.post("tasks", {**body, "model": "unverified-model"})
            self.assertEqual((status, denied["error"]), (409, "MODEL_NOT_VERIFIED"))
            transport.assert_not_called()


if __name__ == "__main__":
    unittest.main()
