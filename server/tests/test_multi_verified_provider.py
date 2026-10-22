"""Tests only synthetic providers; no API calls, payments or cloud deployment."""
import tempfile
import unittest
from unittest.mock import patch

from server.gateway import Denied, Gateway, Store
from server.multi_verified_provider import VerifiedProviderPool
from server.owner_gateway_provider import provider_from_env


class FakeModel:
    def __init__(self, name, model, *, fail_probe=False, fail_chat=False):
        self.name = name
        self.model = model
        self.fail_probe = fail_probe
        self.fail_chat = fail_chat
        self.calls = []

    def configured(self):
        return True

    def candidates(self):
        return (self.model,)

    def reply(self, model, message, *, probe=False):
        self.calls.append((model, message, probe))
        if (probe and self.fail_probe) or (not probe and self.fail_chat):
            raise Denied("SYNTHETIC_DOWN", 502)
        if model != self.model:
            raise Denied("SYNTHETIC_WRONG_MODEL")
        return "Sentetik cevap", model, 1


def settings(**overrides):
    cfg = {"KRAL_MULTI_ROUTER_APPROVED": "YES",
           "KRAL_MULTI_COST_APPROVED": "YES",
           "KRAL_MULTI_PROVIDERS": "openai,cloudflare_workers_ai"}
    cfg.update(overrides)
    return cfg


def pool(cfg=None, left=None, right=None):
    left = left or FakeModel("openai", "openai-synthetic")
    right = right or FakeModel("cloudflare_workers_ai", "@cf/meta/llama-3.2-3b-instruct")
    p = VerifiedProviderPool(
        providers={"openai": left, "cloudflare_workers_ai": right},
        environ=settings() if cfg is None else cfg)
    return p, left, right


class MultiVerifiedRouterTests(unittest.TestCase):
    def test_default_deny_before_any_probe_or_network(self):
        for change in (
                {"KRAL_MULTI_ROUTER_APPROVED": "NO"},
                {"KRAL_MULTI_COST_APPROVED": "NO"},
                {"KRAL_MULTI_ROUTER_APPROVED": "yes"},
                {"KRAL_MULTI_COST_APPROVED": ""},
                {"KRAL_MULTI_PROVIDERS": ""},
                {"KRAL_MULTI_PROVIDERS": "openai,unknown"},
                {"KRAL_MULTI_PROVIDERS": "openai,openai"},
                {"KRAL_MULTI_PROVIDERS": "owner_gateway,openai,owner_gateway"}):
            cfg = settings(**change)
            instance, left, right = pool(cfg)
            with self.subTest(change=change), tempfile.TemporaryDirectory() as td:
                self.assertFalse(instance.configured())
                result = Gateway(Store(td + "/history.db"), instance).verified_models()
                self.assertEqual(result["models"], [])
                self.assertEqual(left.calls, [])
                self.assertEqual(right.calls, [])

    def test_two_models_keep_own_provider_identity_in_history(self):
        instance, left, right = pool()
        with tempfile.TemporaryDirectory() as td:
            gateway = Gateway(Store(td + "/history.db"), instance)
            models = gateway.verified_models()["models"]
            self.assertEqual({m["provider"] for m in models},
                             {"openai", "cloudflare_workers_ai"})
            cloud = next(m for m in models if m["provider"] == "cloudflare_workers_ai")
            response = gateway.chat({"message": "Merhaba", "model": cloud["id"]})
            self.assertEqual(response["provider"], "cloudflare_workers_ai")
            self.assertEqual(gateway.store.history()[-1]["provider"], "cloudflare_workers_ai")
            self.assertEqual(len(left.calls), 1)  # one probe, no cross-provider chat
            self.assertEqual(len(right.calls), 2)

    def test_one_upstream_probe_failure_keeps_other_verified_model(self):
        instance, left, right = pool(
            right=FakeModel("cloudflare_workers_ai",
                            "@cf/meta/llama-3.2-3b-instruct", fail_probe=True))
        with tempfile.TemporaryDirectory() as td:
            gateway = Gateway(Store(td + "/history.db"), instance)
            result = gateway.verified_models()
            self.assertEqual([m["provider"] for m in result["models"]], ["openai"])
            self.assertEqual(result["errors"], [{"code": "SYNTHETIC_DOWN"}])
            response = gateway.chat({"message": "Selam", "model": "openai-synthetic"})
            self.assertEqual(response["provider"], "openai")
            self.assertEqual(len(right.calls), 1)

    def test_same_returned_id_from_two_providers_blocks_both(self):
        same = "shared-synthetic-model"
        # Two OpenAI-compatible providers can report the same unqualified ID.
        # Cloudflare @cf/... IDs cannot collide with ordinary model IDs.
        left = FakeModel("openai", same)
        right = FakeModel("owner_gateway", same)
        instance = VerifiedProviderPool(
            providers={"openai": left, "owner_gateway": right},
            environ=settings(KRAL_MULTI_PROVIDERS="openai,owner_gateway"))
        with tempfile.TemporaryDirectory() as td:
            gateway = Gateway(Store(td + "/history.db"), instance)
            result = gateway.verified_models()
            self.assertEqual(result["models"], [])
            self.assertEqual(result["errors"], [{"code": "MODEL_PROVIDER_COLLISION"}])
            with self.assertRaises(Denied) as caught:
                gateway.chat({"message": "Don't send", "model": same})
            self.assertEqual(caught.exception.code, "MODEL_NOT_VERIFIED")
            self.assertEqual(len(left.calls), 1)
            self.assertEqual(len(right.calls), 1)

    def test_revoked_permission_blocks_even_cached_verified_model(self):
        cfg = settings()
        instance, left, right = pool(cfg)
        with tempfile.TemporaryDirectory() as td:
            gateway = Gateway(Store(td + "/history.db"), instance)
            self.assertEqual(len(gateway.verified_models()["models"]), 2)
            cfg["KRAL_MULTI_COST_APPROVED"] = "NO"
            with self.assertRaises(Denied) as err:
                gateway.chat({"message": "Do not send", "model": "openai-synthetic"})
            self.assertEqual(err.exception.code, "MULTI_ROUTE_DENIED")
            self.assertEqual(len(left.calls), 1)

    def test_single_provider_stays_default_without_pool(self):
        with patch.dict("os.environ", {"KRAL_PROVIDER_MODE": "openai"}, clear=True):
            self.assertEqual(provider_from_env().name, "openai")
        with patch.dict("os.environ", {"KRAL_PROVIDER_MODE": "multi_verified"}, clear=True):
            self.assertIsInstance(provider_from_env(), VerifiedProviderPool)
            self.assertFalse(provider_from_env().configured())

    def test_malformed_route_and_nonexistent_model_are_denied(self):
        instance, left, right = pool()
        for candidate in ("openai-synthetic", ("not-allowed", "x"),
                          ("openai", "not-allowlisted"), ("openai",),
                          ("openai", "abc", "extra")):
            with self.subTest(candidate=candidate), self.assertRaises(Denied):
                instance.reply(candidate, "text")
        self.assertEqual(left.calls, [])
        self.assertEqual(right.calls, [])


if __name__ == "__main__":
    unittest.main()
