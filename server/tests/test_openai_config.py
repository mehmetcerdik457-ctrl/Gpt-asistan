"""Credential aliases stay server-only and share the existing API transports."""
import io
import json
import os
import unittest
from unittest.mock import Mock, patch

from server import gateway
from server.openai_model_inventory import collect_inventory


class OpenAIConfigurationTests(unittest.TestCase):
    @staticmethod
    def response():
        response = io.BytesIO(gateway.json_bytes({
            "id": "resp_config_fixture", "status": "completed", "model": "fixture-model",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "Fixture answer"}]}],
        }))
        response.status, response.headers = 200, {"x-request-id": "req_config_fixture"}
        return response

    def test_managed_alias_authenticates_existing_responses_transport(self):
        for canonical in (None, "", "   "):
            with self.subTest(canonical=canonical):
                with patch.dict(os.environ, {"OPENAI_API_KEY": "", "KRAL_OPENAI_API_KEY": " synthetic-alias-token "}), \
                     patch("server.gateway.urllib.request.build_opener") as transport:
                    if canonical is None:
                        os.environ.pop("OPENAI_API_KEY", None)
                    else:
                        os.environ["OPENAI_API_KEY"] = canonical
                    transport.return_value.open.return_value = self.response()
                    provider = gateway.OpenAIProvider()
                    self.assertTrue(provider.configured())
                    answer, model, _, metadata = provider.reply_with_metadata("fixture-model", "Fixture task")
                    request = transport.return_value.open.call_args.args[0]
                    self.assertEqual(request.full_url, "https://api.openai.com/v1/responses")
                    self.assertEqual(request.get_header("Authorization"), "Bearer synthetic-alias-token")
                    self.assertNotIn("synthetic-alias-token", request.data.decode("utf-8"))
                    self.assertEqual((answer, model), ("Fixture answer", "fixture-model"))
                    self.assertNotIn("synthetic-alias-token", json.dumps(metadata))

    def test_canonical_credential_takes_precedence_over_managed_alias(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": " synthetic-canonical-token ",
                                     "KRAL_OPENAI_API_KEY": "synthetic-alias-token"}), \
             patch("server.gateway.urllib.request.build_opener") as transport:
            transport.return_value.open.return_value = self.response()
            gateway.OpenAIProvider().reply("fixture-model", "Fixture task")
            request = transport.return_value.open.call_args.args[0]
            self.assertEqual(request.get_header("Authorization"), "Bearer synthetic-canonical-token")
            self.assertNotIn("synthetic-alias-token", str(request.header_items()))

    def test_missing_canonical_and_alias_are_rejected_before_transport(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "", "KRAL_OPENAI_API_KEY": "   "}), \
             patch("server.gateway.urllib.request.build_opener") as transport:
            provider = gateway.OpenAIProvider()
            self.assertFalse(provider.configured())
            with self.assertRaises(gateway.Denied) as caught:
                provider.reply("fixture-model", "Fixture task")
            self.assertEqual((caught.exception.code, caught.exception.status),
                             ("PROVIDER_NOT_CONFIGURED", 503))
            transport.assert_not_called()

    def test_model_configuration_cannot_treat_active_credentials_as_models(self):
        key = "synthetic-private-credential"
        for key_name in ("OPENAI_API_KEY", "KRAL_OPENAI_API_KEY"):
            for model in (key, "model_" + key):
                with self.subTest(key_name=key_name, prefixed=model != key), \
                     patch.dict(os.environ, {"OPENAI_API_KEY": "", "KRAL_OPENAI_API_KEY": "",
                                             key_name: key, "OPENAI_ALLOWED_MODELS": "fixture-model," + model}), \
                     patch("server.gateway.urllib.request.build_opener") as transport:
                    with self.assertRaises(gateway.Denied) as caught:
                        gateway.OpenAIProvider().candidates()
                    self.assertEqual(caught.exception.code, "MODEL_CONFIGURATION_INVALID")
                    self.assertNotIn(key, str(caught.exception))
                    transport.assert_not_called()

    def test_inventory_uses_same_alias_without_exposing_it_or_claiming_live_access(self):
        values = {"KRAL_OPENAI_API_KEY": "synthetic-alias-token", "OPENAI_ALLOWED_MODELS": "gpt-6.1-sol"}
        transport = Mock()
        offline = collect_inventory(values, opener=transport)
        self.assertTrue(offline["key_present_server_side"])
        self.assertEqual(offline["mode"], "OFFLINE_NO_NETWORK")
        transport.open.assert_not_called()
        response = io.BytesIO(gateway.json_bytes({"object": "list", "data": [{"id": "gpt-6.1-sol"}]}))
        response.status = 200
        transport.open.return_value = response
        catalog = collect_inventory(values, check_api=True, opener=transport)
        request = transport.open.call_args.args[0]
        self.assertEqual((request.get_method(), request.full_url), ("GET", "https://api.openai.com/v1/models"))
        self.assertEqual(request.get_header("Authorization"), "Bearer synthetic-alias-token")
        self.assertIsNone(request.data)
        self.assertEqual(catalog["catalog_result"], "READ_ONLY_GET_SUCCEEDED_NOT_LIVE_VERIFIED")
        self.assertEqual(catalog["live_responses_calls_made"], 0)
        self.assertFalse(catalog["account_entitlement_fully_verified"])
        self.assertNotIn("synthetic-alias-token", json.dumps({"offline": offline, "catalog": catalog}))


if __name__ == "__main__":
    unittest.main()
