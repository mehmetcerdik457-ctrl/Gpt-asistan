"""Synthetic upstream reflection must never return the configured provider key."""
from io import BytesIO
import json
import os
import unittest
import urllib.error
from unittest.mock import patch

from server import gateway as g


class ProviderSecretReflectionTests(unittest.TestCase):
    key = "synthetic-provider-key-12345"

    @staticmethod
    def payload():
        return {"id": "resp_synthetic_123", "status": "completed", "model": "snapshot-synthetic",
                "output": [{"type": "message", "content": [
                    {"type": "output_text", "text": "Synthetic reply"}]}]}

    @staticmethod
    def response(payload, headers=None, status=200):
        response = BytesIO(g.json_bytes(payload))
        response.status = status
        response.headers = headers or {}
        return response

    def invoke(self, response=None, error=None):
        with patch.dict(os.environ, {"OPENAI_API_KEY": self.key}), \
             patch("urllib.request.build_opener") as opener:
            if error is not None:
                opener.return_value.open.side_effect = error
            else:
                opener.return_value.open.return_value = response
            return g.OpenAIProvider().reply_with_metadata("requested", "synthetic prompt")

    def assert_error_redacted(self, error):
        self.assertNotIn(self.key, str(error))
        self.assertNotIn(self.key, json.dumps(vars(error), default=str))

    def test_http_error_request_id_cannot_echo_key_or_key_substring(self):
        for value in (self.key, "req_" + self.key + "_suffix"):
            with self.subTest(reflection=value):
                error = urllib.error.HTTPError(
                    "https://api.openai.com/v1/responses", 401, "synthetic upstream error",
                    {"x-request-id": value}, BytesIO(g.json_bytes({"error": {"code": "invalid_api_key"}})))
                with self.assertRaises(g.Denied) as denied:
                    self.invoke(error=error)
                self.assertIsNone(denied.exception.provider_request_id)
                self.assertEqual(denied.exception.provider_error_code, "invalid_api_key")
                self.assert_error_redacted(denied.exception)

    def test_http_error_code_cannot_echo_key_or_key_substring(self):
        for value in (self.key, "error_" + self.key + "_suffix"):
            with self.subTest(reflection=value):
                error = urllib.error.HTTPError(
                    "https://api.openai.com/v1/responses", 429, "synthetic upstream error",
                    {"x-request-id": "req_synthetic_123"},
                    BytesIO(g.json_bytes({"error": {"code": value}})))
                with self.assertRaises(g.Denied) as denied:
                    self.invoke(error=error)
                self.assertIsNone(denied.exception.provider_error_code)
                self.assertEqual(denied.exception.provider_request_id, "req_synthetic_123")
                self.assert_error_redacted(denied.exception)

    def test_success_request_id_cannot_echo_key(self):
        result = self.invoke(self.response(self.payload(), {"x-request-id": "req_" + self.key}))
        self.assertEqual(result[0], "Synthetic reply")
        self.assertIsNone(result[3]["request_id"])
        self.assertNotIn(self.key, json.dumps(result))

    def test_non200_response_request_id_cannot_echo_key(self):
        with self.assertRaises(g.Denied) as denied:
            self.invoke(self.response({}, {"x-request-id": "req_" + self.key}, status=403))
        self.assertIsNone(denied.exception.provider_request_id)
        self.assert_error_redacted(denied.exception)

    def test_completed_response_rejects_key_in_text_model_or_response_id(self):
        for field in ("text", "model", "id"):
            with self.subTest(field=field):
                payload = self.payload()
                if field == "text":
                    payload["output"][0]["content"][0]["text"] = "reflected " + self.key
                else:
                    payload[field] = "reflected_" + self.key
                with self.assertRaises(g.Denied) as denied:
                    self.invoke(self.response(payload, {"x-request-id": "req_synthetic_123"}))
                self.assertEqual(denied.exception.status, 502)
                self.assert_error_redacted(denied.exception)


if __name__ == "__main__":
    unittest.main()
