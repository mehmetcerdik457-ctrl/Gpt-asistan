"""Synthetic HTTP only. These tests do not contact Cloudflare."""
import json
import os
import unittest
import urllib.error
from email.message import Message
from tempfile import TemporaryDirectory
from unittest.mock import patch

from server.cloudflare_workers_ai_provider import CloudflareWorkersAIProvider
from server.gateway import Denied, Gateway, Store
from server.owner_gateway_provider import provider_from_env

MODEL = "@cf/meta/llama-3.2-3b-instruct"
ACCOUNT = "a" * 32
TOKEN = "not-a-real-cloudflare-token-1234"
URL = "https://api.cloudflare.com/client/v4/accounts/" + ACCOUNT + "/ai/run/" + MODEL


def env():
    return {"KRAL_CLOUDFLARE_MODEL": MODEL, "KRAL_CLOUDFLARE_ACCOUNT_ID": ACCOUNT,
            "KRAL_CLOUDFLARE_API_TOKEN": TOKEN,
            "KRAL_CLOUDFLARE_COST_APPROVED": "YES"}


class FakeResponse:
    status = 200

    def __init__(self, payload, content_type="application/json"):
        self.payload = payload
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, n):
        return self.payload[:n]


class FakeOpener:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        return self.response


def success():
    return FakeResponse(json.dumps({"success": True, "errors": [],
                                    "result": {"response": "Merhaba"}}).encode())


class AdapterTests(unittest.TestCase):
    def test_explicit_cost_approval_blocks_all_network_before_request(self):
        for value in (None, "", "NO", "yes", "True"):
            with self.subTest(value=value):
                cfg = env()
                if value is None:
                    cfg.pop("KRAL_CLOUDFLARE_COST_APPROVED")
                else:
                    cfg["KRAL_CLOUDFLARE_COST_APPROVED"] = value
                with patch("server.cloudflare_workers_ai_provider.urllib.request.build_opener") as opener:
                    p = CloudflareWorkersAIProvider(cfg)
                    self.assertFalse(p.configured())
                    with self.assertRaises(Denied) as raised:
                        p.reply(MODEL, "Do not send this upstream")
                    self.assertEqual(raised.exception.code, "CLOUDFLARE_NOT_CONFIGURED")
                    opener.assert_not_called()

    def test_absent_settings_fail_closed(self):
        for name in env():
            config = env()
            config[name] = ""
            p = CloudflareWorkersAIProvider(config)
            self.assertFalse(p.configured())
            with self.assertRaises(Denied):
                p.candidates()

    def test_validate_account_token_model_and_no_other_model(self):
        for key, bad in [
            ("KRAL_CLOUDFLARE_ACCOUNT_ID", "a" * 31),
            ("KRAL_CLOUDFLARE_MODEL", "@cf/meta/../internal"),
            ("KRAL_CLOUDFLARE_MODEL", "https://evil.test/x"),
            ("KRAL_CLOUDFLARE_MODEL", "openai/gpt-5.5"),
            ("KRAL_CLOUDFLARE_API_TOKEN", "line\ninjection"),
            ("KRAL_CLOUDFLARE_API_TOKEN", "spaces are not tokens"),
        ]:
            config = env()
            config[key] = bad
            self.assertFalse(CloudflareWorkersAIProvider(config).configured())
        with self.assertRaises(Denied):
            CloudflareWorkersAIProvider(env()).reply("@cf/meta/other", "hi")

    def test_pinned_real_api_route_and_bounded_probe(self):
        opener = FakeOpener(success())
        with patch("server.cloudflare_workers_ai_provider.urllib.request.build_opener", return_value=opener):
            answer, model, ms = CloudflareWorkersAIProvider(env()).reply(MODEL, "Selam", probe=True)
        self.assertEqual((answer, model), ("Merhaba", MODEL))
        self.assertGreaterEqual(ms, 0)
        req, timeout = opener.calls[0]
        self.assertEqual((req.full_url, req.get_method(), timeout), (URL, "POST", 10))
        self.assertEqual(req.get_header("Authorization"), "Bearer " + TOKEN)
        self.assertEqual(json.loads(req.data), {
            "messages": [{"role": "user", "content": "Selam"}], "stream": False, "max_tokens": 64})

    def test_bad_response_never_counts_as_model_verification(self):
        invalid = [
            b"", b"x", b"[]", b"{}", b'{"success":false,"result":{"response":"hi"}}',
            b'{"success":true,"errors":[{"code":1}],"result":{"response":"hi"}}',
            b'{"success":true,"result":{"response":""}}',
            b'{"success":true,"result":{"response":[1]}}',
            b"a" * 131073,
        ]
        for raw in invalid:
            with self.subTest(size=len(raw)):
                with patch("server.cloudflare_workers_ai_provider.urllib.request.build_opener",
                           return_value=FakeOpener(FakeResponse(raw))):
                    with self.assertRaises(Denied):
                        CloudflareWorkersAIProvider(env()).reply(MODEL, "hi")

    def test_error_bodies_never_returned_and_no_fallback(self):
        with patch("server.cloudflare_workers_ai_provider.urllib.request.build_opener",
                   return_value=FakeOpener(FakeResponse(b"<html>", "text/html"))):
            with self.assertRaises(Denied):
                CloudflareWorkersAIProvider(env()).reply(MODEL, "hi")
        for code, expected in [(401, "CLOUDFLARE_AUTH_DENIED"), (429, "CLOUDFLARE_RATE_OR_QUOTA")]:
            def fail(*args, **kwargs):
                raise urllib.error.HTTPError(URL, code, "mock", Message(), None)
            with patch("server.cloudflare_workers_ai_provider.urllib.request.build_opener") as factory:
                factory.return_value.open.side_effect = fail
                with self.assertRaises(Denied) as caught:
                    CloudflareWorkersAIProvider(env()).reply(MODEL, "hi")
                self.assertEqual(caught.exception.code, expected)

    def test_cloudflare_model_is_visible_to_owner_gateway_and_usable_for_chat(self):
        # Regression: the @cf/ prefix used to be rejected by the shared
        # OpenAI model ID validator, even after a successful upstream probe.
        opener = FakeOpener(success())
        with TemporaryDirectory() as td, patch(
                "server.cloudflare_workers_ai_provider.urllib.request.build_opener",
                return_value=opener):
            gateway = Gateway(Store(td + "/db.sqlite3"), CloudflareWorkersAIProvider(env()))
            discovered = gateway.verified_models()
            self.assertEqual(discovered["errors"], [])
            self.assertEqual([m["id"] for m in discovered["models"]], [MODEL])
            self.assertEqual(discovered["models"][0]["provider"], "cloudflare_workers_ai")
            reply = gateway.chat({"message": "Selam", "model": MODEL})
            self.assertEqual((reply["text"], reply["model"], reply["provider"]),
                             ("Merhaba", MODEL, "cloudflare_workers_ai"))
            self.assertEqual(len(opener.calls), 2)
            self.assertEqual(gateway.store.history()[0]["answer"], "Merhaba")

    def test_existing_owner_gateway_wires_optional_provider(self):
        with TemporaryDirectory() as td, patch.dict(
                os.environ, {"KRAL_PROVIDER_MODE": "cloudflare_workers_ai", **env()}):
            selected = provider_from_env()
            self.assertIsInstance(selected, CloudflareWorkersAIProvider)
            gateway = Gateway(Store(td + "/db.sqlite3"))
            self.assertEqual(gateway.provider.candidates(), (MODEL,))


if __name__ == "__main__":
    unittest.main()
