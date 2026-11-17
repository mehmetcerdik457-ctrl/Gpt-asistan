"""Gemini provider adapter and SUPER ADMIN status contract tests."""
import json
import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch
import urllib.error

from server.gateway import (
    CompositeProvider, Denied, Gateway, GeminiProvider, PREFIX, Store,
)


class FakeResponse(BytesIO):
    status = 200
    headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class GeminiProviderTests(unittest.TestCase):
    def test_interactions_api_request_is_server_keyed_and_store_false(self):
        key = "synthetic-gemini-secret"
        body = json.dumps({
            "object": "interaction",
            "status": "completed",
            "id": "v1_test_interaction_01",
            "model": "gemini-test-flash",
            "steps": [{"type": "model_output", "content": [
                {"type": "text", "text": "Merhaba KRAL"}
            ]}],
        }).encode()
        transport = Mock()
        transport.open.return_value = FakeResponse(body)
        with patch.dict(os.environ, {"GEMINI_API_KEY": key}, clear=True), \
             patch("server.gateway.urllib.request.build_opener", return_value=transport):
            text, model, elapsed, metadata = GeminiProvider().reply_with_metadata(
                "gemini-test-flash", "Yalnızca Merhaba yaz.", probe=True,
                client_request_id="request_01",
            )
        request = transport.open.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, GeminiProvider.endpoint_base + "/v1beta/interactions")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("X-goog-api-key"), key)
        self.assertEqual(payload, {
            "model": "gemini-test-flash",
            "input": "Yalnızca Merhaba yaz.",
            "store": False,
        })
        self.assertEqual((text, model), ("Merhaba KRAL", "gemini-test-flash"))
        self.assertGreaterEqual(elapsed, 0)
        self.assertEqual(metadata["response_id"], "v1_test_interaction_01")
        self.assertIsNone(metadata["request_id"])
        self.assertNotIn(key, repr(metadata))

    def test_provider_http_errors_are_redacted(self):
        key = "synthetic-gemini-secret"
        transport = Mock()
        transport.open.side_effect = urllib.error.HTTPError(
            "https://generativelanguage.googleapis.com/v1beta/interactions", 403, "hidden", {}, BytesIO(key.encode())
        )
        with patch.dict(os.environ, {"GEMINI_API_KEY": key}, clear=True), \
             patch("server.gateway.urllib.request.build_opener", return_value=transport):
            with self.assertRaises(Denied) as caught:
                GeminiProvider().reply("gemini-test-flash", "hello")
        self.assertEqual(caught.exception.code, "PROVIDER_MODEL_OR_PERMISSION_DENIED")
        self.assertNotIn(key, str(caught.exception))

    def test_allowlist_is_explicit_and_rejects_non_gemini_ids(self):
        with patch.dict(os.environ, {
            "GEMINI_API_KEY": "synthetic",
            "GEMINI_ALLOWED_MODELS": "gemini-test-flash,gemini-test-pro",
            "GEMINI_MODEL_PREFERRED": "gemini-test-pro",
        }, clear=True):
            self.assertEqual(
                GeminiProvider().candidates(),
                ("gemini-test-pro", "gemini-test-flash"),
            )
        with patch.dict(os.environ, {
            "GEMINI_API_KEY": "synthetic",
            "GEMINI_ALLOWED_MODELS": "gpt-test",
        }, clear=True):
            with self.assertRaisesRegex(Denied, "GEMINI_MODEL_CONFIGURATION_INVALID"):
                GeminiProvider().candidates()

    def test_api_version_defaults_to_v1beta_and_rejects_unknown_values(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                GeminiProvider().endpoint_url(),
                "https://generativelanguage.googleapis.com/v1beta/interactions",
            )
        with patch.dict(os.environ, {"GEMINI_API_VERSION": "v2"}, clear=True):
            with self.assertRaisesRegex(Denied, "GEMINI_API_VERSION_INVALID"):
                GeminiProvider().endpoint_url()

    def test_gemini_background_mode_fails_closed(self):
        with self.assertRaisesRegex(Denied, "GEMINI_BACKGROUND_UNSUPPORTED"):
            GeminiProvider().start_background("gemini-test-flash", "hello")

    def test_composite_provider_routes_without_cross_provider_fallback(self):
        with patch.dict(os.environ, {
            "OPENAI_API_KEY": "synthetic-openai",
            "OPENAI_ALLOWED_MODELS": "gpt-test",
            "GEMINI_API_KEY": "synthetic-gemini",
            "GEMINI_ALLOWED_MODELS": "gemini-test-flash",
        }, clear=True):
            provider = CompositeProvider()
            self.assertEqual(provider.candidates(), ("gpt-test", "gemini-test-flash"))
            self.assertEqual(provider.provider_name("gpt-test"), "openai")
            self.assertEqual(provider.provider_name("gemini-test-flash"), "gemini")

    def test_super_admin_status_is_read_only_and_never_returns_secret_values(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            gateway = Gateway(Store(Path(directory) / "kral.sqlite3"))
            result = gateway.route(PREFIX + "admin/status", {})
        self.assertEqual(result["role"], "SUPER_ADMIN")
        self.assertEqual(result["authorization"], "DUAL_P256_OWNER_DEVICE")
        self.assertFalse(result["credential_values_exposed"])
        self.assertFalse(result["external_actions_enabled"])
        self.assertEqual(result["google_drive"], "NOT_CONFIGURED_IN_KRAL_BACKEND")
        gemini = next(row for row in result["providers"] if row["id"] == "gemini")
        self.assertEqual(gemini["api_version"], "v1beta")
        self.assertNotIn("api_key", json.dumps(result).lower())


if __name__ == "__main__":
    unittest.main()
