"""OpenAI model-list inventory is read-only, explicit, and never fabricates access."""
import json
from io import BytesIO
import urllib.error
import unittest
from unittest.mock import Mock

from server.openai_model_inventory import (
    API_MODELS_URL, CatalogError, collect_inventory, parse_catalog,
    read_project_catalog, RejectRedirects,
)


class CatalogResponse(BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class OpenAIModelInventoryTests(unittest.TestCase):
    def test_offline_inventory_does_not_need_key_or_call_api(self):
        transport = Mock()
        report = collect_inventory(
            {"OPENAI_ALLOWED_MODELS": "gpt-6.1-sol,gpt-5.6-sol"},
            check_api=False, opener=transport)
        transport.open.assert_not_called()
        self.assertEqual(report["mode"], "OFFLINE_NO_NETWORK")
        self.assertFalse(report["key_present_server_side"])
        self.assertEqual(report["catalog_result"], "NOT_CHECKED")
        self.assertTrue(next(row for row in report["models"]
                             if row["model_id"] == "gpt-6.1-sol")["configured_in_gateway_allowlist"])
        self.assertTrue(all(row["listed_in_connected_api_project"] is None
                            and not row["responses_call_verified"] for row in report["models"]))

    def test_explicit_get_only_and_catalog_list_not_live_entitlement(self):
        transport = Mock()
        transport.open.return_value = CatalogResponse(json.dumps({
            "object": "list", "data": [{"id": "gpt-6.1-sol"}, {"id": "gpt-6-luna"}]
        }).encode())
        report = collect_inventory(
            {"OPENAI_API_KEY": "synthetic-private-token",
             "OPENAI_ALLOWED_MODELS": "gpt-6.1-sol"},
            check_api=True, opener=transport)
        request = transport.open.call_args.args[0]
        self.assertEqual(request.full_url, API_MODELS_URL)
        self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(request.data)
        self.assertEqual(report["live_responses_calls_made"], 0)
        self.assertEqual(report["catalog_result"], "READ_ONLY_GET_SUCCEEDED_NOT_LIVE_VERIFIED")
        present = next(row for row in report["models"] if row["model_id"] == "gpt-6.1-sol")
        self.assertTrue(present["listed_in_connected_api_project"])
        self.assertFalse(present["responses_call_verified"])
        self.assertNotIn("synthetic-private-token", json.dumps(report))

    def test_missing_key_fails_without_network(self):
        transport = Mock()
        result = collect_inventory({}, check_api=True, opener=transport)
        self.assertEqual(result["catalog_result"], "API_KEY_NOT_CONFIGURED")
        transport.open.assert_not_called()

    def test_unsupported_configuration_does_not_assert_active_models(self):
        x = collect_inventory({"OPENAI_ALLOWED_MODELS":
            "gpt-6-astra,gpt-6-sol,gpt-6-luna,gpt-6.1-sol,gpt-6.1-terra"})
        self.assertFalse(x["gateway_allowlist_valid"])
        self.assertFalse(any(m["configured_in_gateway_allowlist"] for m in x["models"]))

    def test_untrusted_model_list_is_rejected(self):
        samples = [b"", b"{", b"{}", b'{"object":"list","data":{}}',
                   b'{"object":"list","data":[{"id":"a"},{"id":"a"}]}',
                   b'{"object":"list","data":[{"id":"../x?"}]}',
                   b'{"object":"list","data":[{"name":"no-id"}]}']
        for raw in samples:
            with self.subTest(raw=raw):
                with self.assertRaises(CatalogError):
                    parse_catalog(raw)

    def test_http_errors_never_reveal_provider_body_or_token(self):
        for status, expected in [(401, "API_KEY_ACCESS_DENIED"),
                                 (403, "API_PROJECT_PERMISSION_DENIED"),
                                 (429, "API_RATE_LIMITED"),
                                 (500, "API_CATALOG_HTTP_ERROR")]:
            transport = Mock()
            transport.open.side_effect = urllib.error.HTTPError(
                API_MODELS_URL, status, "hidden upstream", {},
                BytesIO(b"synthetic-private-token and owner data"))
            with self.subTest(status=status):
                with self.assertRaises(CatalogError) as exc:
                    read_project_catalog("synthetic-private-token", opener=transport)
                self.assertEqual(str(exc.exception), expected)

    def test_redirects_are_denied(self):
        with self.assertRaisesRegex(CatalogError, "API_REDIRECT_DENIED"):
            RejectRedirects().redirect_request(None, None, 302, "redirect", {},
                                               "https://unknown.example")

    def test_network_failure_is_redacted(self):
        transport = Mock()
        transport.open.side_effect = urllib.error.URLError("private host details")
        with self.assertRaisesRegex(CatalogError, "API_NETWORK_UNAVAILABLE"):
            read_project_catalog("synthetic-private-token", opener=transport)

    def test_success_parser_accepts_only_documented_id_shapes(self):
        self.assertEqual(parse_catalog(b'{"object":"list","data":[{"id":"gpt-6.1-sol"}]}'),
                         {"gpt-6.1-sol"})


if __name__ == "__main__":
    unittest.main()
