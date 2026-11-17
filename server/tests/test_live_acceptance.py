"""Acceptance runner tests use synthetic configuration and mocked transport only."""
import contextlib
import hashlib
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import verify_openai_acceptance as acceptance
from server.gateway import Denied
from server.openai_model_inventory import CatalogError


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "OPENAI_API_KEY": "synthetic-private-key",
            "OPENAI_ALLOWED_MODELS": "model-fixture",
        }, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def invoke(self, *argv):
        output = StringIO()
        with contextlib.redirect_stdout(output):
            code = acceptance.main(list(argv))
        return code, json.loads(output.getvalue())

    @staticmethod
    def success():
        return "KRAL_OK", "model-fixture", 12, {
            "response_id": "resp_fixture", "request_id": "req_fixture", "http_status": 200}

    def test_default_is_offline_and_does_not_claim_access(self):
        with patch.object(acceptance.OpenAIProvider, "reply_with_metadata") as provider, \
             patch.object(acceptance, "read_project_catalog") as catalog:
            code, report = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "READY_FOR_AUTHORIZED_CHECK")
        self.assertTrue(report["key_present"])
        self.assertEqual(report["account_access"], "NOT_VERIFIED")
        self.assertEqual(report["model_access"], "NOT_VERIFIED")
        self.assertEqual(report["responses_attempted"], 0)
        self.assertNotIn("synthetic-private-key", json.dumps(report))
        provider.assert_not_called()
        catalog.assert_not_called()

    def test_live_prerequisites_are_required_before_any_network(self):
        cases = [
            (("--live", "--model", "model-fixture"), {}, "PAID_APPROVAL_REQUIRED"),
            (("--live", "--approve-paid"), {}, "EXPLICIT_MODEL_REQUIRED"),
            (("--live", "--approve-paid", "--model", "other-model"), {}, "SELECTED_MODEL_NOT_ALLOWLISTED"),
            (("--live", "--approve-paid", "--model", "model-fixture"),
             {"OPENAI_API_KEY": ""}, "PROVIDER_NOT_CONFIGURED"),
            (("--live", "--approve-paid", "--model", "model-fixture"),
             {"OPENAI_ALLOWED_MODELS": "invalid model"}, "MODEL_CONFIGURATION_INVALID"),
        ]
        for argv, changes, expected in cases:
            with self.subTest(expected=expected), patch.dict(os.environ, changes), \
                 patch.object(acceptance.OpenAIProvider, "reply_with_metadata") as provider, \
                 patch.object(acceptance, "read_project_catalog") as catalog:
                code, report = self.invoke(*argv)
                self.assertNotEqual(code, 0)
                self.assertIn(expected, report["errors"])
                self.assertEqual(report["responses_attempted"], 0)
                provider.assert_not_called()
                catalog.assert_not_called()

    def test_credential_in_configured_model_is_never_reported_or_sent(self):
        key = "synthetic-private-key"
        for key_name in ("OPENAI_API_KEY", "KRAL_OPENAI_API_KEY"):
            for configured in (key, "model_" + key):
                for argv in ((), ("--list-models",),
                             ("--live", "--approve-paid", "--model", configured)):
                    with self.subTest(key_name=key_name, prefixed=configured != key, mode=argv[:1]), \
                         patch.dict(os.environ, {"OPENAI_API_KEY": "", "KRAL_OPENAI_API_KEY": "",
                                                 key_name: key, "OPENAI_ALLOWED_MODELS": configured}), \
                         patch.object(acceptance.OpenAIProvider, "reply_with_metadata") as provider, \
                         patch.object(acceptance, "read_project_catalog") as catalog:
                        code, report = self.invoke(*argv)
                        self.assertEqual(code, 1 if argv else 0)
                        self.assertEqual(report["status"], "BLOCKED")
                        self.assertEqual(report["errors"], ["MODEL_CONFIGURATION_INVALID"])
                        self.assertEqual(report["configured_models"], [])
                        self.assertEqual(report["responses_attempted"], 0)
                        self.assertNotIn("requested_model", report)
                        self.assertNotIn(key, json.dumps(report))
                        provider.assert_not_called()
                        catalog.assert_not_called()

    def test_credential_in_explicit_live_model_is_rejected_without_reflection(self):
        key = "synthetic-private-key"
        for key_name in ("OPENAI_API_KEY", "KRAL_OPENAI_API_KEY"):
            for selected in (key, "model_" + key):
                with self.subTest(key_name=key_name, prefixed=selected != key), \
                     patch.dict(os.environ, {"OPENAI_API_KEY": "", "KRAL_OPENAI_API_KEY": "", key_name: key}), \
                     patch.object(acceptance.OpenAIProvider, "reply_with_metadata") as provider, \
                     patch.object(acceptance, "read_project_catalog") as catalog:
                    code, report = self.invoke("--live", "--approve-paid", "--model", selected)
                    self.assertEqual(code, 1)
                    self.assertEqual(report["errors"], ["SELECTED_MODEL_NOT_ALLOWLISTED"])
                    self.assertNotIn(key, json.dumps(report))
                    self.assertNotIn("requested_model", report)
                    self.assertEqual(report["responses_attempted"], 0)
                    provider.assert_not_called()
                    catalog.assert_not_called()

    def test_inactive_alias_is_also_excluded_from_written_model_evidence(self):
        primary, alias = "synthetic-primary-key", "synthetic-secondary-key"
        with tempfile.TemporaryDirectory() as directory:
            for index, configured in enumerate((alias, "model_" + alias)):
                destination = Path(directory) / f"redacted-{index}.json"
                with self.subTest(prefixed=configured != alias), \
                     patch.dict(os.environ, {"OPENAI_API_KEY": primary, "KRAL_OPENAI_API_KEY": alias,
                                             "OPENAI_ALLOWED_MODELS": configured}), \
                     patch.object(acceptance.OpenAIProvider, "reply_with_metadata") as provider, \
                     patch.object(acceptance, "read_project_catalog") as catalog:
                    code, report = self.invoke("--output", str(destination))
                    self.assertEqual(code, 0)
                    self.assertEqual(report["status"], "BLOCKED")
                    self.assertEqual(report["errors"], ["MODEL_CONFIGURATION_INVALID"])
                    self.assertEqual(report["configured_models"], [])
                    self.assertEqual(json.loads(destination.read_text()), report)
                    for secret in (primary, alias):
                        self.assertNotIn(secret, destination.read_text())
                        self.assertNotIn(secret, json.dumps(report))
                    provider.assert_not_called()
                    catalog.assert_not_called()

    def test_model_list_is_get_only_and_does_not_assert_response_access(self):
        with patch.object(acceptance.OpenAIProvider, "reply_with_metadata") as provider, \
             patch.object(acceptance, "read_project_catalog", return_value={"model-fixture", "another"}) as catalog:
            code, report = self.invoke("--list-models")
        self.assertEqual(code, 0)
        catalog.assert_called_once_with("synthetic-private-key")
        provider.assert_not_called()
        self.assertEqual(report["catalog_count"], 2)
        self.assertEqual(report["configured_models_listed"], {"model-fixture": True})
        self.assertEqual(report["model_access"], "CATALOG_PRESENCE_ONLY_NOT_RESPONSES_VERIFIED")
        self.assertEqual(report["responses_attempted"], 0)

    def test_read_only_catalog_can_be_checked_before_a_live_model_is_configured(self):
        with patch.dict(os.environ, {"OPENAI_ALLOWED_MODELS": ""}), \
             patch.object(acceptance.OpenAIProvider, "reply_with_metadata") as provider, \
             patch.object(acceptance, "read_project_catalog", return_value={"model-fixture"}) as catalog:
            code, report = self.invoke("--list-models")
        self.assertEqual(code, 0)
        self.assertEqual(report["configured_models"], [])
        self.assertEqual(report["catalog_count"], 1)
        self.assertEqual(report["model_access"], "CATALOG_PRESENCE_ONLY_NOT_RESPONSES_VERIFIED")
        self.assertEqual(report["responses_attempted"], 0)
        catalog.assert_called_once_with("synthetic-private-key")
        provider.assert_not_called()

    def test_catalog_failure_and_missing_listing_are_blockers(self):
        with patch.object(acceptance, "read_project_catalog", side_effect=CatalogError("API_KEY_ACCESS_DENIED")):
            code, report = self.invoke("--list-models")
        self.assertEqual(code, 1)
        self.assertEqual(report["errors"], ["API_KEY_ACCESS_DENIED"])
        with patch.object(acceptance, "read_project_catalog", return_value=set()):
            code, report = self.invoke("--list-models")
        self.assertEqual(code, 1)
        self.assertEqual(report["errors"], ["CONFIGURED_MODEL_NOT_LISTED"])

    def test_approved_live_check_calls_adapter_once_and_records_safe_evidence(self):
        with patch.object(acceptance.OpenAIProvider, "reply_with_metadata", return_value=self.success()) as provider, \
             patch.object(acceptance, "read_project_catalog") as catalog:
            code, report = self.invoke("--live", "--approve-paid", "--model", "model-fixture")
        self.assertEqual(code, 0)
        provider.assert_called_once()
        catalog.assert_not_called()
        args, kwargs = provider.call_args
        self.assertEqual(args, ("model-fixture", "Reply with exactly KRAL_OK."))
        self.assertTrue(kwargs["probe"])
        self.assertEqual(kwargs["client_request_id"], report["client_request_id"])
        self.assertEqual(kwargs["request_metadata"], {
            "request_id": report["client_request_id"], "kral_acceptance": "oct26"})
        self.assertEqual(report["responses_attempted"], 1)
        self.assertEqual(report["response_id"], "resp_fixture")
        self.assertEqual(report["provider_request_id"], "req_fixture")
        self.assertEqual(report["requested_model"], "model-fixture")
        self.assertEqual(report["returned_model"], "model-fixture")
        self.assertEqual(report["output_sha256"], hashlib.sha256(b"KRAL_OK").hexdigest())
        self.assertTrue(report["output_matches_fixture"])
        self.assertNotIn("synthetic-private-key", json.dumps(report))

    def test_real_adapter_mocked_transport_enforces_one_64_token_request(self):
        response = BytesIO(json.dumps({
            "id": "resp_mocked", "status": "completed", "model": "model-fixture",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "KRAL_OK"}]}],
        }).encode())
        response.status = 200
        response.headers = {"x-request-id": "req_mocked"}
        with patch("urllib.request.build_opener") as transport:
            transport.return_value.open.return_value = response
            code, report = self.invoke("--live", "--approve-paid", "--model", "model-fixture")
        self.assertEqual(code, 0)
        transport.return_value.open.assert_called_once()
        request = transport.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.openai.com/v1/responses")
        payload = json.loads(request.data)
        self.assertEqual(payload["max_output_tokens"], 64)
        self.assertFalse(payload["store"])
        self.assertEqual(payload["input"][1]["content"], "Reply with exactly KRAL_OK.")
        self.assertEqual(report["response_id"], "resp_mocked")

    def test_401_and_unknown_failures_are_redacted_and_never_replayed(self):
        for error, code in ((Denied("PROVIDER_AUTH_DENIED", 502), "PROVIDER_AUTH_DENIED"),
                            (RuntimeError("synthetic-private-key personal content"), "ACCEPTANCE_CHECK_FAILED")):
            with self.subTest(code=code), \
                 patch.object(acceptance.OpenAIProvider, "reply_with_metadata", side_effect=error) as provider:
                exit_code, report = self.invoke("--live", "--approve-paid", "--model", "model-fixture")
                self.assertEqual(exit_code, 1)
                self.assertEqual(report["errors"], [code])
                self.assertEqual(report["responses_attempted"], 1)
                provider.assert_called_once()
                self.assertNotIn("synthetic-private-key", json.dumps(report))
                self.assertNotIn("personal content", json.dumps(report))

    def test_fixture_mismatch_is_failed_without_retry_or_raw_output(self):
        with patch.object(acceptance.OpenAIProvider, "reply_with_metadata", return_value=(
                "private unexpected answer", "model-fixture", 9,
                {"response_id": "resp_fixture", "request_id": "req_fixture"})) as provider:
            code, report = self.invoke("--live", "--approve-paid", "--model", "model-fixture")
        self.assertEqual(code, 1)
        self.assertEqual(report["errors"], ["LIVE_FIXTURE_MISMATCH"])
        self.assertNotIn("private unexpected answer", json.dumps(report))
        provider.assert_called_once()

    def test_output_is_redacted_and_existing_evidence_prevents_a_paid_call(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            code, report = self.invoke("--output", str(path))
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(path.read_text()), report)
            original = path.read_text()
            with patch.object(acceptance.OpenAIProvider, "reply_with_metadata") as provider:
                code, report = self.invoke("--live", "--approve-paid", "--model", "model-fixture",
                                           "--output", str(path))
            self.assertEqual(code, 1)
            self.assertEqual(report["errors"], ["EVIDENCE_WRITE_FAILED"])
            self.assertEqual(path.read_text(), original)
            provider.assert_not_called()


if __name__ == "__main__":
    unittest.main()
