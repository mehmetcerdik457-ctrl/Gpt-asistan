"""Owner HTTPS model adapter; synthetic HTTP only (never contacts CİHAT)."""
import json
import os
import unittest
from email.message import Message
from unittest.mock import patch
from server.gateway import Denied, Gateway, Store
from server.owner_gateway_provider import (
    OwnerGatewayProvider, XAIProvider, normalized_messages, provider_from_env, valid_endpoint
)

HOST = "kral.example.org"
URL = "https://kral.example.org/v1/chat/completions"
MODEL = "owner-approved-model"

def config():
    return {
        "KRAL_OWNER_GATEWAY_URL": URL,
        "KRAL_OWNER_GATEWAY_HOST": HOST,
        "KRAL_OWNER_GATEWAY_TOKEN": "placeholder-not-a-real-secret",
        "KRAL_OWNER_GATEWAY_MODEL": MODEL,
    }

class Response:
    status = 200
    def __init__(self, payload, kind="application/json"):
        self.payload = payload
        self.headers = Message()
        self.headers["Content-Type"] = kind
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def read(self, count):
        return self.payload[:count]

class Opener:
    def __init__(self, response):
        self.response = response
        self.calls = []
    def open(self, req, timeout):
        self.calls.append((req, timeout))
        return self.response

def good():
    return Response(json.dumps({
        "model": MODEL,
        "choices": [{"message": {"role": "assistant", "content": "Merhaba Cihat"}}]
    }).encode())

class OwnerAdapterTests(unittest.TestCase):
    def test_strict_public_https_endpoint(self):
        self.assertTrue(valid_endpoint(URL, HOST))
        bad = [
            "http://kral.example.org/v1/chat/completions",
            "https://kral.example.org:8443/v1/chat/completions",
            "https://user:pass@kral.example.org/v1/chat/completions",
            "https://kral.example.org/v1/chat/completions?token=bad",
            "https://kral.example.org/v1/chat/completions#frag",
            "https://evil.example.org/v1/chat/completions",
            "https://127.0.0.1/v1/chat/completions",
            "https://kral.example.org/admin",
            "https://kral.example.org./v1/chat/completions",
        ]
        for item in bad:
            with self.subTest(endpoint=item):
                self.assertFalse(valid_endpoint(item, HOST))
        self.assertFalse(valid_endpoint("https://127.0.0.1/v1/chat/completions", "127.0.0.1"))
        self.assertFalse(valid_endpoint("https://kral.example.org/v1/chat/completions", "internal"))

    def test_missing_or_corrupted_configuration_fails_closed(self):
        cfg = config()
        for key in cfg:
            with self.subTest(key=key):
                env = cfg.copy()
                env[key] = ""
                p = OwnerGatewayProvider(env)
                self.assertFalse(p.configured())
                with self.assertRaises(Denied):
                    p.candidates()
                with self.assertRaises(Denied):
                    p.reply(MODEL, "Hello")
        cfg["KRAL_OWNER_GATEWAY_TOKEN"] = "foo\nbar"
        self.assertFalse(OwnerGatewayProvider(cfg).configured())

    def test_model_allowlist_enforced(self):
        p = OwnerGatewayProvider(config())
        self.assertEqual(p.candidates(), (MODEL,))
        with self.assertRaises(Denied):
            p.reply("other-model", "Hello")

    def test_exact_authenticated_request_and_verified_reply(self):
        opener = Opener(good())
        with patch("server.owner_gateway_provider.urllib.request.build_opener", return_value=opener):
            answer, actual, duration = OwnerGatewayProvider(config()).reply(MODEL, "Selam", probe=True)
        self.assertEqual((answer, actual), ("Merhaba Cihat", MODEL))
        self.assertGreaterEqual(duration, 0)
        req, timeout = opener.calls[0]
        self.assertEqual(req.full_url, URL)
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(timeout, 10)
        self.assertEqual(req.get_header("Authorization"), "Bearer placeholder-not-a-real-secret")
        data = json.loads(req.data)
        self.assertEqual(data["messages"], [{"role": "user", "content": "Selam"}])
        self.assertFalse(data["stream"])
        self.assertEqual(data["max_tokens"], 64)

    def test_role_and_context_validation(self):
        input_context = [
            {"role": "user", "content": "Soru"},
            {"role": "assistant", "content": "Yanıt"},
            {"role": "user", "content": "Yeni soru"},
        ]
        self.assertEqual(normalized_messages(input_context), input_context)
        for invalid in (
            [], {}, None, "", "a" * 12001, [{"role": "system", "content": "bad"}],
            [{"role": "tool", "content": "bad"}], [{"role": "user", "content": ""}],
            [{"role": "user", "content": ["image"]}], [{"role": "user", "content": "x", "tool_call": True}],
            [{"role": "user", "content": "x"}] * 10,
        ):
            with self.subTest(value=str(invalid)[:45]):
                with self.assertRaises(Denied):
                    normalized_messages(invalid)

    def test_response_validation_blocks_false_success(self):
        malformed = [
            b"",
            b"not-json",
            b"[]",
            b"{}",
            json.dumps({"model": "wrong", "choices": [{"message": {"content": "hi"}}]}).encode(),
            json.dumps({"model": MODEL, "choices": []}).encode(),
            json.dumps({"model": MODEL, "choices": [{"message": {"content": ""}}]}).encode(),
            json.dumps({"model": MODEL, "choices": [{"message": {"content": {"tool_call": "bad"}}}]}).encode(),
            b"a" * 131073,
        ]
        for value in malformed:
            with self.subTest(payload=str(value)[:32]):
                with patch("server.owner_gateway_provider.urllib.request.build_opener",
                           return_value=Opener(Response(value))):
                    with self.assertRaises(Denied):
                        OwnerGatewayProvider(config()).reply(MODEL, "Soru")

    def test_non_json_rejected(self):
        with patch("server.owner_gateway_provider.urllib.request.build_opener",
                   return_value=Opener(Response(b"<html>Bad</html>", "text/html"))):
            with self.assertRaises(Denied):
                OwnerGatewayProvider(config()).reply(MODEL, "Soru")

    def test_redirect_fails_closed(self):
        from server.gateway import NoRedirect
        with self.assertRaises(Denied):
            NoRedirect().redirect_request(None, None, 302, "Moved", {}, "https://other.example")

    def test_model_selector_never_falls_back(self):
        with patch.dict(os.environ, {"KRAL_PROVIDER_MODE": "owner_gateway", **config()}, clear=False):
            provider = provider_from_env()
            self.assertIsInstance(provider, OwnerGatewayProvider)
            self.assertTrue(provider.configured())
        with patch.dict(os.environ, {"KRAL_PROVIDER_MODE": "invalid"}, clear=False):
            with self.assertRaises(Denied):
                provider_from_env()
        with patch.dict(os.environ, {"KRAL_PROVIDER_MODE": "openai"}, clear=False):
            self.assertEqual(provider_from_env().name, "openai")

    def test_existing_gateway_uses_selected_provider(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as directory, \
             patch.dict(os.environ, {"KRAL_PROVIDER_MODE": "owner_gateway", **config()}, clear=False):
            selected = Gateway(Store(directory + "/db.sqlite3")).provider
            self.assertEqual(selected.name, "owner_gateway")
            self.assertEqual(selected.candidates(), (MODEL,))


class XAIProviderTests(unittest.TestCase):
    """All upstream traffic is mocked. These do not assert live xAI access."""
    def credentials(self):
        return {"XAI_API_KEY": "synthetic-not-a-real-key-00001",
                "XAI_MODEL": "grok-4.5"}

    def test_official_url_is_fixed_and_model_explicit(self):
        env = {**self.credentials(),
               "KRAL_OWNER_GATEWAY_URL": "https://evil.example/v1/chat/completions",
               "KRAL_OWNER_GATEWAY_HOST": "evil.example",
               "KRAL_OWNER_GATEWAY_TOKEN": "do-not-use"}
        provider = XAIProvider(env)
        self.assertEqual(provider.name, "xai")
        self.assertTrue(provider.configured())
        self.assertEqual(provider.candidates(), ("grok-4.5",))
        response = Response(json.dumps({
            "model": "grok-4.5",
            "choices": [{"message": {"content": "Merhaba"}}],
        }).encode())
        opener = Opener(response)
        with patch("server.owner_gateway_provider.urllib.request.build_opener",
                   return_value=opener):
            result = provider.reply("grok-4.5", "Merhaba", probe=True)
        self.assertEqual(result[:2], ("Merhaba", "grok-4.5"))
        request, timeout = opener.calls[0]
        self.assertEqual(request.full_url, "https://api.x.ai/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"),
                         "Bearer synthetic-not-a-real-key-00001")
        self.assertNotIn("do-not-use", str(request.header_items()))
        self.assertEqual(timeout, 10)
        body = json.loads(request.data)
        self.assertEqual(body["messages"], [{"role": "user", "content": "Merhaba"}])
        self.assertFalse(body["stream"])

    def test_missing_or_malformed_credentials_fail_without_network(self):
        for env in ({}, {"XAI_MODEL": "grok-4.5"},
                    {"XAI_API_KEY": "short", "XAI_MODEL": "grok-4.5"},
                    {"XAI_API_KEY": "valid-looking-test-token-123", "XAI_MODEL": ""},
                    {"XAI_API_KEY": "valid-looking-test-token-123\nheader",
                     "XAI_MODEL": "grok-4.5"},
                    {"XAI_API_KEY": "valid-looking-test-token-123",
                     "XAI_MODEL": "invalid model id"}):
            with self.subTest(env_keys=list(env)):
                provider = XAIProvider(env)
                self.assertFalse(provider.configured())
                with patch("server.owner_gateway_provider.urllib.request.build_opener") as open_:
                    with self.assertRaises(Denied):
                        provider.reply("grok-4.5", "Merhaba")
                    open_.assert_not_called()

    def test_unapproved_model_or_changed_identity_rejected(self):
        provider = XAIProvider(self.credentials())
        with self.assertRaises(Denied):
            provider.reply("other-model", "Hi")
        response = Response(json.dumps({
            "model": "unexpected-model",
            "choices": [{"message": {"content": "Merhaba"}}],
        }).encode())
        with patch("server.owner_gateway_provider.urllib.request.build_opener",
                   return_value=Opener(response)):
            with self.assertRaises(Denied) as context:
                provider.reply("grok-4.5", "Hi")
        self.assertEqual(context.exception.code, "OWNER_GATEWAY_RESPONSE_INVALID")

    def test_selector_wires_existing_gateway_without_silent_fallback(self):
        from tempfile import TemporaryDirectory
        with patch.dict(os.environ, {"KRAL_PROVIDER_MODE": "xai",
                                      **self.credentials()}, clear=True):
            provider = provider_from_env()
            self.assertIsInstance(provider, XAIProvider)
            self.assertEqual(provider.name, "xai")
            with TemporaryDirectory() as directory:
                gateway = Gateway(Store(directory + "/db.sqlite3"))
                self.assertIsInstance(gateway.provider, XAIProvider)
                self.assertEqual(gateway.provider.candidates(), ("grok-4.5",))
        with patch.dict(os.environ, {"KRAL_PROVIDER_MODE": "xai",
                                      "OPENAI_API_KEY": "irrelevant-secret"}, clear=True):
            selected = provider_from_env()
            self.assertFalse(selected.configured())
            with self.assertRaises(Denied):
                selected.candidates()

if __name__ == "__main__":
    unittest.main()
