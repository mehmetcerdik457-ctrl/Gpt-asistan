"""OpenAI webhook ingress: signature, freshness, durable receipt and replay tests."""
import base64
import hashlib
import hmac
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from server import gateway as g
from server import openai_webhooks


class UnusedProvider:
    name = "openai"
    def start_background(self, model, prompt, *, request_metadata=None, client_request_id=None):
        return {"response_id": "resp_test_001", "request_id": "req_background_test",
                "http_status": 200, "status": "in_progress"}
    def retrieve_background(self, response_id):
        if response_id != "resp_test_001":
            raise AssertionError("unexpected response id")
        return "synthetic webhook answer", "model-fixture", {
            "response_id": response_id, "request_id": "req_retrieve_test",
            "http_status": 200, "retryable": False,
        }


def make_event(event_id="evt_test_001"):
    return json.dumps({
        "object": "event",
        "id": event_id,
        "type": "response.completed",
        "created_at": 1760000000,
        "data": {"id": "resp_test_001"},
    }, separators=(",", ":")).encode("utf-8")


def signed_headers(body, secret, webhook_id="wh_test_001", timestamp=None):
    timestamp = str(int(time.time()) if timestamp is None else timestamp)
    key = base64.b64decode(secret[6:] + "=" * (-len(secret[6:]) % 4))
    signed = webhook_id.encode() + b"." + timestamp.encode() + b"." + body
    signature = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    return {
        "Content-Type": "application/json",
        "webhook-id": webhook_id,
        "webhook-timestamp": timestamp,
        "webhook-signature": "v1," + signature,
    }


class OpenAIWebhookVerifierTests(unittest.TestCase):
    def setUp(self):
        self.key = b"test-webhook-signing-key-32-bytes"
        self.secret = "whsec_" + base64.b64encode(self.key).decode().rstrip("=")
        self.body = make_event()

    def test_verifies_raw_body_and_parses_event(self):
        headers = signed_headers(self.body, self.secret, timestamp=1000)
        event, delivery_id = openai_webhooks.verify_and_parse(
            self.body, headers, self.secret, now=1000
        )
        self.assertEqual(event["type"], "response.completed")
        self.assertEqual(delivery_id, "wh_test_001")

    def test_rejects_modified_body_and_bad_signature(self):
        headers = signed_headers(self.body, self.secret, timestamp=1000)
        with self.assertRaises(openai_webhooks.WebhookError) as error:
            openai_webhooks.verify_and_parse(self.body + b" ", headers, self.secret, now=1000)
        self.assertEqual(error.exception.code, "WEBHOOK_SIGNATURE_INVALID")

    def test_rejects_stale_and_future_timestamps(self):
        for timestamp in (699, 1301):
            headers = signed_headers(self.body, self.secret, timestamp=timestamp)
            with self.assertRaises(openai_webhooks.WebhookError) as error:
                openai_webhooks.verify_and_parse(self.body, headers, self.secret, now=1000)
            self.assertEqual(error.exception.code, "WEBHOOK_TIMESTAMP_OUT_OF_RANGE")

    def test_requires_secret_and_required_headers(self):
        with self.assertRaises(openai_webhooks.WebhookError) as error:
            openai_webhooks.verify_and_parse(self.body, {}, "")
        self.assertEqual(error.exception.code, "WEBHOOK_SECRET_NOT_CONFIGURED")
        with self.assertRaises(openai_webhooks.WebhookError):
            openai_webhooks.verify_and_parse(self.body, {}, self.secret)

    def test_rejects_malformed_or_oversized_event(self):
        headers = signed_headers(b"{}", self.secret, timestamp=1000)
        with self.assertRaises(openai_webhooks.WebhookError) as error:
            openai_webhooks.verify_and_parse(b"{}", headers, self.secret, now=1000)
        self.assertEqual(error.exception.code, "WEBHOOK_EVENT_INVALID")
        with self.assertRaises(openai_webhooks.WebhookError) as error:
            openai_webhooks.verify_and_parse(b"x" * (openai_webhooks.MAX_WEBHOOK_BODY + 1),
                                             headers, self.secret, now=1000)
        self.assertEqual(error.exception.status, 413)


class OpenAIWebhookHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "gateway.sqlite3")
        self.key = b"test-webhook-signing-key-32-bytes"
        self.secret = "whsec_" + base64.b64encode(self.key).decode().rstrip("=")
        self.env = patch.dict(os.environ, {"OPENAI_WEBHOOK_SECRET": self.secret})
        self.env.start()
        self.gateway = g.Gateway(g.Store(self.db), UnusedProvider(), otp=object())
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), g.handler_for(self.gateway))
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:" + str(self.httpd.server_port)

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=3)
        self.gateway.tasks.pool.shutdown(wait=True, cancel_futures=True)
        self.env.stop()
        self.tmp.cleanup()

    def post(self, body, headers):
        request = urllib.request.Request(
            self.url + "/webhooks/openai", data=body, method="POST", headers=headers
        )
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def test_public_signed_endpoint_accepts_without_owner_p256_headers(self):
        body = make_event(event_type="response.queued")
        status, data = self.post(body, signed_headers(body, self.secret))
        self.assertEqual(status, 200)
        self.assertTrue(data["accepted"])
        self.assertFalse(data["duplicate"])
        self.assertEqual(data["event_type"], "response.queued")

    def test_duplicate_delivery_is_acknowledged_once(self):
        body = make_event(event_type="response.queued")
        headers = signed_headers(body, self.secret)
        first = self.post(body, headers)
        second = self.post(body, headers)
        self.assertEqual(first[0], 200)
        self.assertEqual(second[0], 200)
        self.assertTrue(second[1]["duplicate"])
        with self.gateway.store.connect() as db:
            count = db.execute("SELECT COUNT(*) FROM openai_webhook_events").fetchone()[0]
        self.assertEqual(count, 1)

    def test_delivery_id_conflict_is_rejected(self):
        first_body = make_event("evt_first", event_type="response.queued")
        second_body = make_event("evt_second", event_type="response.queued")
        self.assertEqual(self.post(first_body, signed_headers(first_body, self.secret))[0], 200)
        status, data = self.post(
            second_body, signed_headers(second_body, self.secret, webhook_id="wh_test_001")
        )
        self.assertEqual((status, data["error"]), (409, "WEBHOOK_ID_CONFLICT"))

    def test_response_completed_webhook_updates_matching_background_task(self):
        task = self.gateway.tasks.submit(
            "model-fixture", "model-fixture", "test-engineer",
            "Webhook-backed task", background=True
        )
        deadline = time.time() + 3
        while time.time() < deadline:
            current = self.gateway.tasks.get(task["task_id"])
            if current["status"] == "background_pending":
                break
            time.sleep(0.01)
        self.assertEqual(current["status"], "background_pending")
        body = make_event()
        headers = signed_headers(body, self.secret)
        status, data = self.post(body, headers)
        self.assertEqual(status, 200)
        self.assertTrue(data["accepted"])
        completed = self.gateway.tasks.get(task["task_id"])
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["result"], "synthetic webhook answer")
        self.assertEqual(completed["response_id"], "resp_test_001")

    def test_unmatched_response_webhook_is_not_acknowledged_or_recorded(self):
        body = make_event()
        status, data = self.post(body, signed_headers(body, self.secret))
        self.assertEqual(status, 503)
        self.assertEqual(data["error"], "WEBHOOK_RESPONSE_NOT_MATCHED")
        with self.gateway.store.connect() as db:
            count = db.execute("SELECT COUNT(*) FROM openai_webhook_events").fetchone()[0]
        self.assertEqual(count, 0)

    def test_invalid_signature_is_rejected(self):
        body = make_event()
        headers = signed_headers(body, self.secret)
        headers["webhook-signature"] = "v1," + base64.b64encode(b"wrong").decode()
        status, data = self.post(body, headers)
        self.assertEqual((status, data["error"]), (400, "WEBHOOK_SIGNATURE_INVALID"))

    def test_missing_secret_fails_closed(self):
        with patch.dict(os.environ, {"OPENAI_WEBHOOK_SECRET": ""}):
            body = make_event()
            status, data = self.post(body, signed_headers(body, self.secret))
        self.assertEqual((status, data["error"]), (503, "WEBHOOK_SECRET_NOT_CONFIGURED"))


if __name__ == "__main__":
    unittest.main()
