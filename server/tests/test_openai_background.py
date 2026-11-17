"""OpenAI Responses background adapter tests; no network or paid API calls."""
import json
import os
import unittest
from unittest.mock import patch

from server.gateway import OpenAIProvider


class FakeResponse:
    status = 200
    headers = {"x-request-id": "req_fake_background"}
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def read(self, limit=-1):
        return self.payload[:limit]


class FakeOpener:
    def __init__(self, payload):
        self.payload = payload
        self.request = None
        self.timeout = None
    def open(self, request, timeout=None):
        self.request = request
        self.timeout = timeout
        return FakeResponse(self.payload)


class OpenAIBackgroundProviderTests(unittest.TestCase):
    def setUp(self):
        self.provider = OpenAIProvider()
        self.env = patch.dict(os.environ, {"OPENAI_API_KEY": "synthetic-test-key"})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_background_submission_explicitly_sets_store_false(self):
        opener = FakeOpener({
            "id": "resp_background_fake", "model": "model-fixture", "status": "in_progress"
        })
        with patch("server.gateway.urllib.request.build_opener", return_value=opener):
            result = self.provider.start_background(
                "model-fixture", "synthetic prompt",
                request_metadata={"kral_task_id": "a" * 32},
                client_request_id="a" * 32,
            )
        payload = json.loads(opener.request.data)
        self.assertEqual(opener.request.full_url, "https://api.openai.com/v1/responses")
        self.assertEqual(payload["background"], True)
        self.assertIs(payload["store"], False)
        self.assertEqual(payload["input"], "synthetic prompt")
        self.assertEqual(result["response_id"], "resp_background_fake")
        self.assertEqual(result["request_id"], "req_fake_background")

    def test_retrieve_accepts_only_the_known_response_id_and_completed_output(self):
        opener = FakeOpener({
            "id": "resp_background_fake", "model": "model-fixture", "status": "completed",
            "output": [{"type": "message", "content": [
                {"type": "output_text", "text": "synthetic completed answer"}
            ]}],
        })
        with patch("server.gateway.urllib.request.build_opener", return_value=opener):
            answer, model, metadata = self.provider.retrieve_background("resp_background_fake")
        self.assertEqual(opener.request.get_method(), "GET")
        self.assertEqual(opener.request.full_url,
                         "https://api.openai.com/v1/responses/resp_background_fake")
        self.assertEqual((answer, model), ("synthetic completed answer", "model-fixture"))
        self.assertEqual(metadata["response_id"], "resp_background_fake")

    def test_retrieve_rejects_non_completed_response(self):
        opener = FakeOpener({
            "id": "resp_background_fake", "model": "model-fixture", "status": "in_progress",
            "output": [],
        })
        with patch("server.gateway.urllib.request.build_opener", return_value=opener):
            with self.assertRaisesRegex(Exception, "PROVIDER_BACKGROUND_NOT_COMPLETED"):
                self.provider.retrieve_background("resp_background_fake")


if __name__ == "__main__":
    unittest.main()
