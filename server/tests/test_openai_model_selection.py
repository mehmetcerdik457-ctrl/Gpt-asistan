"""Signed owner HTTP requests with a synthetic OpenAI transport; no live API calls."""
from io import BytesIO
import json
import os
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from server import gateway as g
from server.tests import test_gateway as fixtures


class OpenAIModelSelectionHttpTests(unittest.TestCase):
    signed = fixtures.GatewayHttpTests.signed

    def setUp(self):
        fixtures.GatewayHttpTests.setUp(self)
        self.model_env = patch.dict(os.environ, {
            "OPENAI_API_KEY": "synthetic-test-key",
            "OPENAI_ALLOWED_MODELS": "legacy-mini-only",
        })
        self.model_env.start()
        os.environ.pop("OPENAI_MODEL", None)
        self.provider = g.OpenAIProvider()
        self.gateway.provider = self.provider
        # Build the real local HTTP client before replacing only the provider's
        # opener factory. Owner requests still cross the HTTP signature gate.
        self.client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.requests = []
        self.actual_model = None
        self.upstream_status = 200
        self.upstream_error = {}
        self.transport = patch("server.gateway.urllib.request.build_opener")
        self.opener = self.transport.start().return_value
        self.opener.open.side_effect = self.upstream

    def tearDown(self):
        self.transport.stop()
        self.model_env.stop()
        fixtures.GatewayHttpTests.tearDown(self)

    def upstream(self, request, **kwargs):
        self.requests.append(request)
        if self.upstream_status != 200:
            raise urllib.error.HTTPError(
                request.full_url, self.upstream_status, "upstream detail must stay private", {},
                BytesIO(g.json_bytes({"error": self.upstream_error})))
        requested = json.loads(request.data)["model"]
        response = BytesIO(g.json_bytes({
            "status": "completed", "model": self.actual_model or requested,
            "output": [{"type": "message", "content": [
                {"type": "output_text", "text": "Merhaba"}]}],
        }))
        response.status = 200
        return response

    def post_chat(self, data, *, unsigned=False):
        path = g.PREFIX + "chat"
        raw = g.json_bytes(data)
        headers = ({"Content-Type": "application/json"} if unsigned
                   else self.signed(path, raw))
        request = urllib.request.Request(self.url + path, data=raw, method="POST", headers=headers)
        try:
            response = self.client.open(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def assert_one_selected_request(self, model):
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0].full_url, "https://api.openai.com/v1/responses")
        body = json.loads(self.requests[0].data)
        self.assertEqual(body["model"], model)
        self.assertFalse(body["store"])

    def test_explicit_unlisted_model_works_without_discovery(self):
        self.assertEqual(self.gateway.models, {})
        status, data = self.post_chat({"message": "Merhaba", "model": "owner-full-model-v9"})
        self.assertEqual(status, 200)
        self.assertEqual(data["requested_model"], "owner-full-model-v9")
        self.assertEqual(data["model"], "owner-full-model-v9")
        self.assertEqual(data["provider"], "openai")
        self.assert_one_selected_request("owner-full-model-v9")

    def test_omitted_model_uses_full_default_not_legacy_mini(self):
        status, data = self.post_chat({"message": "Merhaba"})
        self.assertEqual(status, 200)
        self.assertEqual(data["requested_model"], "gpt-4.1")
        self.assertEqual(data["model"], "gpt-4.1")
        self.assert_one_selected_request("gpt-4.1")

    def test_configured_default_ignores_legacy_choice_list(self):
        with patch.dict(os.environ, {"OPENAI_MODEL": "owner-selected-model"}):
            status, data = self.post_chat({"message": "Merhaba"})
        self.assertEqual(status, 200)
        self.assertEqual(data["requested_model"], "owner-selected-model")
        self.assert_one_selected_request("owner-selected-model")

    def test_stale_discovery_cannot_block_or_replace_explicit_choice(self):
        self.gateway.models["gpt-4o"] = ({
            "id": "gpt-4o", "provider": "openai",
            "verified_at": int(time.time()) - g.MODEL_TTL - 1,
        }, "gpt-4o-mini")
        status, data = self.post_chat({"message": "Merhaba", "model": "gpt-4o"})
        self.assertEqual(status, 200)
        self.assertEqual(data["model"], "gpt-4o")
        self.assert_one_selected_request("gpt-4o")

    def test_dated_snapshot_preserves_requested_alias_in_response(self):
        self.actual_model = "gpt-4o-2024-11-20"
        status, data = self.post_chat({"message": "Merhaba", "model": "gpt-4o"})
        self.assertEqual(status, 200)
        self.assertEqual(data["requested_model"], "gpt-4o")
        self.assertEqual(data["model"], "gpt-4o-2024-11-20")
        self.assert_one_selected_request("gpt-4o")

    def test_mini_response_is_not_accepted_as_full_model_snapshot(self):
        self.actual_model = "gpt-4o-mini-2024-07-18"
        status, data = self.post_chat({"message": "Merhaba", "model": "gpt-4o"})
        self.assertEqual((status, data["error"]), (409, "PROVIDER_MODEL_CHANGED"))
        self.assert_one_selected_request("gpt-4o")

    def test_invalid_explicit_model_never_reaches_provider(self):
        for model in (None, "", "white space", "line\nbreak", [], 7):
            with self.subTest(model=model):
                status, _ = self.post_chat({"message": "Merhaba", "model": model})
                self.assertEqual(status, 400)
        self.assertEqual(self.requests, [])

    def test_explicit_choice_still_requires_owner_signatures(self):
        status, data = self.post_chat(
            {"message": "Merhaba", "model": "owner-full-model-v9"}, unsigned=True)
        self.assertEqual((status, data["error"]), (403, "OWNER_AUTH_REQUIRED"))
        self.assertEqual(self.requests, [])

    def test_insufficient_quota_requests_once_without_downgrade(self):
        self.upstream_status = 429
        self.upstream_error = {
            "code": "insufficient_quota", "type": "insufficient_quota",
            "message": "synthetic-test-key private billing details",
        }
        status, data = self.post_chat({"message": "Merhaba", "model": "gpt-4o"})
        self.assertEqual((status, data["error"]), (502, "PROVIDER_INSUFFICIENT_QUOTA"))
        self.assertEqual(data["message"], "Hesaba bakiye yükle. Seçilen model değiştirilmedi.")
        self.assertNotIn("synthetic-test-key", json.dumps(data))
        self.assertNotIn("private billing details", json.dumps(data))
        self.assert_one_selected_request("gpt-4o")

    def test_billing_hard_limit_is_reported_without_retry(self):
        self.upstream_status = 429
        self.upstream_error = {"code": "billing_hard_limit_reached"}
        status, data = self.post_chat({"message": "Merhaba", "model": "gpt-4.1"})
        self.assertEqual((status, data["error"]), (502, "PROVIDER_INSUFFICIENT_QUOTA"))
        self.assert_one_selected_request("gpt-4.1")

    def test_quota_type_without_code_is_reported_without_retry(self):
        self.upstream_status = 429
        self.upstream_error = {"type": "insufficient_quota"}
        status, data = self.post_chat({"message": "Merhaba", "model": "gpt-4o"})
        self.assertEqual((status, data["error"]), (502, "PROVIDER_INSUFFICIENT_QUOTA"))
        self.assert_one_selected_request("gpt-4o")

    def test_missing_provider_key_never_reaches_upstream(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            status, data = self.post_chat({"message": "Merhaba", "model": "gpt-4o"})
        self.assertEqual((status, data["error"]), (503, "PROVIDER_NOT_CONFIGURED"))
        self.assertEqual(self.requests, [])

    def test_rate_limit_does_not_trigger_a_cheaper_model_or_retry(self):
        self.upstream_status = 429
        self.upstream_error = {"code": "rate_limit_exceeded", "type": "requests"}
        status, data = self.post_chat({"message": "Merhaba", "model": "gpt-4o"})
        self.assertEqual((status, data["error"]), (502, "PROVIDER_QUOTA_OR_RATE_LIMIT"))
        self.assertNotIn("Hesaba bakiye yükle", json.dumps(data, ensure_ascii=False))
        self.assert_one_selected_request("gpt-4o")

    def test_upstream_model_access_error_is_not_a_local_allowlist_or_fallback(self):
        self.upstream_status = 400
        self.upstream_error = {"code": "model_not_found"}
        status, data = self.post_chat({"message": "Merhaba", "model": "owner-unlisted-full-model"})
        self.assertEqual((status, data["error"]), (502, "PROVIDER_HTTP_FAILURE"))
        self.assert_one_selected_request("owner-unlisted-full-model")


if __name__ == "__main__":
    unittest.main()
