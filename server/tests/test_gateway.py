"""Real HTTP and P-256 crypto, synthetic upstream. No live provider/device claim."""
import base64
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
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from server import gateway as g
from server import owner_auth_v1 as auth
from server.enroll import validated_env


def b64(value):
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def der(key):
    return key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


class SyntheticProvider:
    name = "openai"
    available = True
    actual = "synthetic-snapshot-001"
    answer = "Sentetik Türkçe yanıt"

    def __init__(self):
        self.calls = []

    def configured(self):
        return self.available

    def candidates(self):
        return ("synthetic-alias",)

    def reply(self, model, message, *, probe=False):
        self.calls.append((model, message, probe))
        return self.answer, self.actual, 2


class GatewayHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.owner = ec.generate_private_key(ec.SECP256R1())
        self.device = ec.generate_private_key(ec.SECP256R1())
        self.identity = hashlib.sha256(der(self.device)).hexdigest()
        self.env = patch.dict(os.environ, {
            "OMEGA_OWNER_ID": "owner-test", "OMEGA_DEVICE_ID": self.identity,
            "OMEGA_OWNER_PUBLIC_DER_B64": b64(der(self.owner)),
            "OMEGA_DEVICE_PUBLIC_DER_B64": b64(der(self.device)),
            "OMEGA_NONCE_DB": self.tmp.name + "/nonces.sqlite3",
        })
        self.env.start()
        self.provider = SyntheticProvider()
        self.db = self.tmp.name + "/data.sqlite3"
        self.gateway = g.Gateway(g.Store(self.db), self.provider)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), g.handler_for(self.gateway))
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:" + str(self.httpd.server_port)

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=3)
        self.env.stop()
        self.tmp.cleanup()

    def signed(self, path, raw, timestamp=None, owner=None, device=None):
        ts = str(int(time.time()) if timestamp is None else timestamp)
        nonce = uuid.uuid4().hex
        owner_id = owner or "owner-test"
        device_id = device or self.identity
        msg = auth.canonical("POST", path, raw, ts, nonce, owner_id, device_id)
        return {"Content-Type": "application/json", "X-Omega-Owner-Id": owner_id,
                "X-Omega-Device-Id": device_id, "X-Omega-Timestamp": ts, "X-Omega-Nonce": nonce,
                "X-Omega-Owner-Proof": b64(self.owner.sign(msg, ec.ECDSA(hashes.SHA256()))),
                "X-Omega-Device-Proof": b64(self.device.sign(msg, ec.ECDSA(hashes.SHA256())))}

    def post(self, route, data, headers=None, **sign_options):
        path = g.PREFIX + route
        raw = data if isinstance(data, bytes) else g.json_bytes(data)
        headers = self.signed(path, raw, **sign_options) if headers is None else headers
        req = urllib.request.Request(self.url + path, data=raw, method="POST", headers=headers)
        try:
            response = urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def verify_model(self):
        status, data = self.post("models", {})
        self.assertEqual(status, 200)
        self.assertEqual(data["contract"], g.CONTRACT)
        self.assertEqual(data["models"][0]["id"], self.provider.actual)
        return data["models"][0]["id"]

    def test_signed_live_probe_contract_and_actual_id(self):
        actual = self.verify_model()
        self.assertNotEqual(actual, self.provider.candidates()[0])
        self.assertTrue(self.provider.calls[0][2])
        status, data = self.post("chat", {"message": "Merhaba", "model": actual, "include_memory": False})
        self.assertEqual(status, 200)
        self.assertEqual(data["text"], self.provider.answer)
        self.assertEqual(data["model"], actual)

    def test_no_provider_calls_without_auth(self):
        status, _ = self.post("models", {}, headers={"Content-Type": "application/json"})
        self.assertEqual(status, 403)
        self.assertEqual(self.provider.calls, [])

    def test_expired_and_future_proof_denied(self):
        for delta in (-120, 120):
            status, data = self.post("models", {}, timestamp=int(time.time()) + delta)
            self.assertEqual((status, data["error"]), (403, "OWNER_AUTH_EXPIRED"))
        self.assertEqual(self.provider.calls, [])

    def test_replay_rejected_after_gateway_recreation(self):
        raw = b"{}"
        headers = self.signed(g.PREFIX + "models", raw)
        self.assertEqual(self.post("models", raw, headers=headers)[0], 200)
        # Nonces belong to SQLite, not Gateway process state.
        self.httpd.RequestHandlerClass = g.handler_for(g.Gateway(g.Store(self.db), self.provider))
        status, data = self.post("models", raw, headers=headers)
        self.assertEqual((status, data["error"]), (403, "OWNER_AUTH_REPLAY_OR_STORAGE_DENIED"))
        self.assertEqual(len(self.provider.calls), 1)

    def test_path_and_body_binding(self):
        raw = b"{}"
        headers = self.signed(g.PREFIX + "chat", raw)
        self.assertEqual(self.post("models", raw, headers=headers)[0], 403)
        headers = self.signed(g.PREFIX + "models", raw)
        self.assertEqual(self.post("models", b'{"other":1}', headers=headers)[0], 403)
        self.assertEqual(self.provider.calls, [])

    def test_both_signatures_required(self):
        for key in ("X-Omega-Owner-Proof", "X-Omega-Device-Proof"):
            headers = self.signed(g.PREFIX + "models", b"{}")
            headers[key] = b64(b"invalid signature")
            self.assertEqual(self.post("models", b"{}", headers=headers)[0], 403)
        self.assertEqual(self.provider.calls, [])

    def test_wrong_owner_and_device_denied(self):
        self.assertEqual(self.post("models", {}, owner="other-owner")[0], 403)
        self.assertEqual(self.post("models", {}, device="f" * 64)[0], 403)
        self.assertEqual(self.provider.calls, [])

    def test_missing_identity_fails_closed(self):
        with patch.dict(os.environ, {"OMEGA_OWNER_PUBLIC_DER_B64": ""}):
            status, data = self.post("models", {})
        self.assertEqual((status, data["error"]), (503, "OWNER_IDENTITY_NOT_PROVISIONED"))
        self.assertEqual(self.provider.calls, [])

    def test_key_identity_must_match_and_keys_must_differ(self):
        with patch.dict(os.environ, {"OMEGA_DEVICE_ID": "f" * 64}):
            self.assertEqual(self.post("models", {}, device="f" * 64)[0], 503)
        with patch.dict(os.environ, {"OMEGA_OWNER_PUBLIC_DER_B64": b64(der(self.device))}):
            self.assertEqual(self.post("models", {})[0], 503)
        self.assertEqual(self.provider.calls, [])

    def test_unverified_model_cannot_make_chat_request(self):
        status, data = self.post("chat", {"message": "Merhaba", "model": "invented"})
        self.assertEqual((status, data["error"]), (409, "MODEL_NOT_VERIFIED"))
        self.assertEqual(self.provider.calls, [])

    def test_expired_verified_model_cannot_make_chat_request(self):
        actual = self.verify_model()
        self.gateway.models[actual][0]["verified_at"] -= g.MODEL_TTL + 1
        status, data = self.post("chat", {"message": "Merhaba", "model": actual})
        self.assertEqual((status, data["error"]), (409, "MODEL_NOT_VERIFIED"))
        self.assertEqual(len(self.provider.calls), 1)

    def test_model_change_invalidates_selection(self):
        actual = self.verify_model()
        self.provider.actual = "different-snapshot"
        self.assertEqual(self.post("chat", {"message": "Merhaba", "model": actual})[0], 409)
        self.assertNotIn(actual, self.gateway.models)
        self.assertEqual(self.gateway.store.history(), [])

    def test_missing_provider_returns_empty_list(self):
        self.verify_model()
        self.provider.available = False
        status, data = self.post("models", {})
        self.assertEqual(status, 200)
        self.assertEqual(data["models"], [])
        self.assertEqual(data["errors"][0]["code"], "PROVIDER_NOT_CONFIGURED")

    def test_empty_probe_text_never_verifies(self):
        self.provider.answer = " "
        status, data = self.post("models", {})
        self.assertEqual(status, 200)
        self.assertEqual(data["models"], [])

    def test_chat_persists_after_store_reopen(self):
        actual = self.verify_model()
        self.post("chat", {"message": "Türkçe: ğüşiöç", "model": actual})
        reopened = g.Store(self.db)
        self.assertEqual(reopened.history()[0]["question"], "Türkçe: ğüşiöç")
        self.assertEqual(reopened.history()[0]["answer"], self.provider.answer)
        status, data = self.post("history", {"limit": 10})
        self.assertEqual(status, 200)
        self.assertEqual(data["messages"][0]["model"], actual)

    def test_memory_recall_after_reopen_and_no_silent_upload(self):
        status, _ = self.post("memory", {"action": "save", "text": "Kahvem şekersiz olsun"})
        self.assertEqual(status, 200)
        self.assertEqual(g.Store(self.db).recall("şekersiz")[0]["text"], "Kahvem şekersiz olsun")
        self.assertEqual(g.Store(self.db).recall("' OR 1=1 --"), [])
        actual = self.verify_model()
        self.post("chat", {"message": "Merhaba", "model": actual})
        self.assertNotIn("şekersiz", self.provider.calls[-1][1])
        self.post("chat", {"message": "Ne biliyorsun?", "model": actual, "include_memory": True})
        self.assertIn("şekersiz", self.provider.calls[-1][1])

    def test_cost_and_body_bounds(self):
        actual = self.verify_model()
        self.assertEqual(self.post("chat", {"message": "a" * 8001, "model": actual})[0], 400)
        self.assertEqual(self.post("models", b"x" * (g.MAX_BODY + 1))[0], 413)
        for _ in range(10):
            self.assertEqual(self.post("chat", {"message": "Merhaba", "model": actual})[0], 200)
        self.assertEqual(self.post("chat", {"message": "Merhaba", "model": actual})[0], 429)

    def test_no_tools_or_unknown_fields(self):
        actual = self.verify_model()
        self.assertEqual(self.post("chat", {"message": "Merhaba", "model": actual, "tools": ["shell"]})[0], 400)
        self.assertEqual(len(self.provider.calls), 1)

    def test_public_registration_validates_distinct_public_keys(self):
        data = {"contract": g.CONTRACT, "owner_id": "owner-test", "device_id": self.identity,
                "owner_public_der_b64": b64(der(self.owner)), "device_public_der_b64": b64(der(self.device))}
        self.assertEqual(validated_env(data)["OMEGA_DEVICE_ID"], self.identity)
        data["device_id"] = "f" * 64
        with self.assertRaises(ValueError):
            validated_env(data)

    def test_reconfigured_owner_cannot_access_stored_chats(self):
        actual = self.verify_model()
        self.post("chat", {"message": "private first owner", "model": actual})
        with patch.dict(os.environ, {"OMEGA_OWNER_ID": "other-owner"}):
            status, data = self.post("history", {}, owner="other-owner")
        self.assertEqual((status, data["error"]), (403, "PERSISTENT_STORE_OWNER_MISMATCH"))
        self.assertNotIn("messages", data)

    def test_unbound_populated_database_needs_explicit_migration(self):
        self.gateway.store.remember("Existing data must not be silently assigned")
        status, data = self.post("history", {})
        self.assertEqual((status, data["error"]), (503, "UNBOUND_EXISTING_STORE_REQUIRES_OWNER_MIGRATION"))


class ProviderTests(unittest.TestCase):
    def response(self, data, status=200):
        from io import BytesIO
        response = BytesIO(g.json_bytes(data))
        response.status = status
        return response

    def invoke(self, response):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "synthetic-test-key"}), patch("urllib.request.build_opener") as mock:
            mock.return_value.open.return_value = response
            result = g.OpenAIProvider().reply("requested", "Merhaba")
            request = mock.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url, "https://api.openai.com/v1/responses")
            self.assertFalse(json.loads(request.data)["store"])
            return result

    def test_completed_response_requires_text_and_actual_model(self):
        payload = {"status": "completed", "model": "actual-snapshot", "output": [
            {"type": "message", "content": [{"type": "output_text", "text": "Merhaba"}]}]}
        self.assertEqual(self.invoke(self.response(payload))[:2], ("Merhaba", "actual-snapshot"))
        for missing in ("model", "output", "status"):
            changed = dict(payload)
            del changed[missing]
            with self.assertRaises(g.Denied):
                self.invoke(self.response(changed))

    def test_http_200_incomplete_is_not_verified(self):
        with self.assertRaises(g.Denied):
            self.invoke(self.response({"status": "incomplete", "model": "actual", "output": []}))

    def test_oversize_response_is_bounded(self):
        with self.assertRaises(g.Denied) as context:
            self.invoke(self.response({"text": "x" * (g.MAX_RESPONSE + 1)}))
        self.assertEqual(context.exception.code, "PROVIDER_RESPONSE_TOO_LARGE")

    def test_redirect_is_denied(self):
        with self.assertRaises(g.Denied):
            g.NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://evil.invalid")

    def test_empty_allowlist_never_invents_models(self):
        with patch.dict(os.environ, {"OPENAI_ALLOWED_MODELS": ""}):
            self.assertEqual(g.OpenAIProvider().candidates(), ())

    def test_upstream_error_body_and_key_are_never_relayed(self):
        from io import BytesIO
        with patch.dict(os.environ, {"OPENAI_API_KEY": "synthetic-sensitive-key"}), patch("urllib.request.build_opener") as mock:
            mock.return_value.open.side_effect = urllib.error.HTTPError(
                "https://api.openai.com/v1/responses", 401, "sensitive error", {},
                BytesIO(b"synthetic-sensitive-key private upstream details"))
            with self.assertRaises(g.Denied) as context:
                g.OpenAIProvider().reply("requested", "Merhaba")
            self.assertEqual(str(context.exception), "PROVIDER_AUTH_DENIED")


if __name__ == "__main__":
    unittest.main()
