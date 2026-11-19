"""Offline preflight safety checks; no real credentials or network calls."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from server.play_preflight import main, preflight
from server.play_runtime import PlayRuntime, RuntimeConfigurationError
from server.tests import test_play_acknowledgement_service as google_fixture


class PlayPreflightTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.path = self.tmp / "private-token-file"
        self.token = "private-purchase-token-never-print"
        self.path.write_text(self.token + "\n")
        self.path.chmod(0o600)
        self.oauth_calls = []
        self.database_calls = []
        self.mutation_calls = []
        self.oauth_value = "private-access-token-never-print"
        self.store = SimpleNamespace(schema="orba", db_factory=self.database)
        self.boundary = SimpleNamespace(
            _store=self.store, _oauth=self.oauth,
            _products=frozenset({google_fixture.PRODUCT}),
            _secret=google_fixture.SECRET, verify=self.forbidden_mutation,
        )
        self.runtime = PlayRuntime(play_boundary=self.boundary)
        self.env = {"OMEGA_OWNER_ID": "alice"}

    def oauth(self):
        self.oauth_calls.append(True)
        return self.oauth_value

    def database(self):
        self.database_calls.append(True)
        raise RuntimeError("PRIVATE_DSN_PASSWORD_AND_HOST")

    def forbidden_mutation(self, *args, **kwargs):
        self.mutation_calls.append(True)
        raise AssertionError("purchase verification must not be called by smoke")

    def builder(self, *, environ):
        self.assertIs(environ, self.env)
        return self.runtime

    def run_check(self, **kwargs):
        return preflight(environ=self.env, runtime_builder=self.builder, **kwargs)

    def lookup(self, **kwargs):
        return self.run_check(purchase_token_file=self.path,
                              product=google_fixture.PRODUCT, **kwargs)

    def test_default_runtime_is_disabled_without_database_or_oauth(self):
        report = preflight(environ={})
        self.assertEqual(report["state"], "DISABLED")
        self.assertFalse(report["ok"])
        self.assertEqual(report["blockers"], [{
            "code": "PLAY_RUNTIME_DISABLED",
            "fields": ["ORBA_PLAY_BOUNDARY_ENABLED", "ORBA_PLAY_RTDN_ENABLED"],
        }])
        self.assertFalse(report["production_acceptance"])

    def test_configured_default_is_offline_and_not_production_acceptance(self):
        report = self.run_check()
        self.assertEqual((report["state"], report["ok"]), ("CONFIGURED", True))
        self.assertEqual(self.oauth_calls, [])
        self.assertEqual(self.database_calls, [])
        for field in ("production_acceptance", "entitlement_granted",
                      "google_play_lookup_verified", "pubsub_oidc_verified"):
            self.assertIs(report[field], False)

    def test_configuration_errors_report_only_fixed_codes_and_field_names(self):
        def invalid(*, environ):
            raise RuntimeConfigurationError("PLAY_RUNTIME_CONFIGURATION_MISSING",
                                            ("ORBA_PLAY_DATABASE_DSN",))
        report = preflight(environ=self.env, runtime_builder=invalid)
        self.assertEqual(report["checks"]["configuration"], {
            "status": "FAILED", "code": "PLAY_RUNTIME_CONFIGURATION_MISSING",
            "fields": ["ORBA_PLAY_DATABASE_DSN"],
        })
        self.assertFalse(report["ok"])

    def test_unexpected_builder_error_never_exposes_credential_or_path(self):
        def invalid(*, environ):
            raise RuntimeError("PRIVATE_DSN_PASSWORD_AND_HOST")
        report = preflight(environ=self.env, runtime_builder=invalid)
        self.assertEqual(report["checks"]["configuration"]["code"], "PLAY_RUNTIME_BUILD_FAILED")
        self.assertNotIn("PRIVATE_DSN_PASSWORD_AND_HOST", json.dumps(report))

    def test_untrusted_configuration_error_strings_are_not_echoed(self):
        def invalid(*, environ):
            raise RuntimeConfigurationError("/private/credential-file", ("password=SECRET",))
        report = preflight(environ=self.env, runtime_builder=invalid)
        self.assertEqual(report["checks"]["configuration"]["code"],
                         "PLAY_RUNTIME_CONFIGURATION_INVALID")
        self.assertNotIn("credential-file", json.dumps(report))
        self.assertNotIn("SECRET", json.dumps(report))

    def test_database_failure_is_fixed_and_does_not_invoke_oauth(self):
        report = self.run_check(check_database=True)
        self.assertEqual(report["checks"]["database"]["code"], "DATABASE_CHECK_UNAVAILABLE")
        self.assertEqual(len(self.database_calls), 1)
        self.assertEqual(self.oauth_calls, [])
        self.assertNotIn("PRIVATE_DSN_PASSWORD_AND_HOST", json.dumps(report))

    def test_explicit_oauth_check_does_not_claim_play_or_pubsub_access(self):
        report = self.run_check(check_oauth=True)
        self.assertEqual(report["checks"]["oauth"], {
            "status": "PASS", "code": "PUBLISHER_OAUTH_OBTAINED"})
        self.assertEqual(len(self.oauth_calls), 1)
        self.assertEqual(self.database_calls, [])
        self.assertFalse(report["google_play_lookup_verified"])
        self.assertFalse(report["pubsub_oidc_verified"])
        self.assertFalse(report["production_acceptance"])
        self.assertNotIn(self.oauth_value, json.dumps(report))

    def test_invalid_oauth_never_reaches_google(self):
        google = google_fixture.FakeGoogle()
        self.oauth_value = "invalid credential\nPRIVATE"
        report = self.lookup(opener=google)
        self.assertEqual(report["checks"]["oauth"]["code"], "PUBLISHER_OAUTH_CHECK_UNAVAILABLE")
        self.assertEqual(report["checks"]["google_play"]["status"], "NOT_RUN")
        self.assertEqual(google.requests, [])
        self.assertNotIn("PRIVATE", json.dumps(report))

    def test_read_only_google_lookup_can_observe_pending_ack_without_post_or_bind(self):
        google = google_fixture.FakeGoogle(google_fixture.purchase())
        report = self.lookup(opener=google)
        self.assertEqual((report["state"], report["ok"]), ("CHECKED", True))
        self.assertTrue(report["google_play_lookup_verified"])
        self.assertEqual([method for method, _ in google.requests], ["GET"])
        self.assertEqual(len(self.oauth_calls), 1)
        self.assertEqual(self.database_calls, [])
        self.assertEqual(self.mutation_calls, [])
        serialized = json.dumps(report)
        for secret in (self.token, self.oauth_value, str(self.path), google_fixture.SECRET.decode()):
            self.assertNotIn(secret, serialized)
        self.assertFalse(report["entitlement_granted"])
        self.assertFalse(report["production_acceptance"])

    def test_wrong_google_owner_is_failed_without_sensitive_error_payload(self):
        google = google_fixture.FakeGoogle(google_fixture.purchase(owner="bob"))
        report = self.lookup(opener=google)
        self.assertEqual(report["checks"]["google_play"]["code"], "GOOGLE_PLAY_LOOKUP_UNAVAILABLE")
        self.assertFalse(report["ok"])
        self.assertFalse(report["google_play_lookup_verified"])
        self.assertNotIn(self.token, json.dumps(report))
        self.assertEqual([method for method, _ in google.requests], ["GET"])

    def test_bad_product_is_rejected_before_file_or_oauth(self):
        report = self.run_check(purchase_token_file="/does-not-exist",
                                product="not-allowed")
        self.assertEqual(report["checks"]["google_play"]["code"], "GOOGLE_PLAY_PRODUCT_NOT_ALLOWED")
        self.assertEqual(self.oauth_calls, [])

    def test_google_flag_requires_token_file_before_oauth(self):
        report = self.run_check(check_google=True, product=google_fixture.PRODUCT)
        self.assertEqual(report["checks"]["google_play"]["code"], "PURCHASE_TOKEN_FILE_REQUIRED")
        self.assertEqual(self.oauth_calls, [])

    def test_rtdn_only_lookup_requires_explicit_authenticated_owner_configuration(self):
        self.env.clear()
        self.runtime = PlayRuntime(rtdn_processor=SimpleNamespace(
            store=self.store, oauth_supplier=self.oauth,
            allowed_products={google_fixture.PRODUCT}, server_secret=google_fixture.SECRET,
        ))
        report = self.lookup()
        self.assertEqual(report["checks"]["google_play"], {
            "status": "FAILED", "code": "GOOGLE_PLAY_OWNER_NOT_CONFIGURED",
            "fields": ["OMEGA_OWNER_ID"],
        })
        self.assertEqual(self.oauth_calls, [])

    def test_different_boundary_and_rtdn_stores_fail_before_external_calls(self):
        self.runtime = PlayRuntime(self.boundary, SimpleNamespace(store=object()))
        report = self.run_check(check_oauth=True, check_database=True)
        self.assertEqual(report["checks"]["configuration"]["code"], "PLAY_RUNTIME_DEPENDENCIES_INVALID")
        self.assertEqual(self.oauth_calls, [])
        self.assertEqual(self.database_calls, [])

    def test_group_readable_token_file_is_rejected_before_oauth(self):
        self.path.chmod(0o640)
        report = self.lookup()
        self.assertEqual(report["checks"]["google_play"]["code"], "PURCHASE_TOKEN_FILE_INVALID")
        self.assertEqual(self.oauth_calls, [])
        self.assertNotIn(str(self.path), json.dumps(report))

    def test_symlink_and_nonregular_token_files_are_rejected(self):
        link = self.tmp / "token-link"
        link.symlink_to(self.path)
        fifo = self.tmp / "token-fifo"
        os.mkfifo(fifo, 0o600)
        for path in (link, fifo, self.tmp):
            with self.subTest(kind=path.name):
                report = self.run_check(purchase_token_file=path,
                                        product=google_fixture.PRODUCT)
                self.assertEqual(report["checks"]["google_play"]["code"], "PURCHASE_TOKEN_FILE_INVALID")
        self.assertEqual(self.oauth_calls, [])

    def test_empty_oversized_or_malformed_token_files_are_rejected(self):
        for content in (b"", b"x" * 4097, b"valid-token\n\n", b"valid token", b"valid\r\n"):
            with self.subTest(length=len(content)):
                self.path.write_bytes(content)
                report = self.lookup()
                self.assertEqual(report["checks"]["google_play"]["code"], "PURCHASE_TOKEN_FILE_INVALID")
        self.assertEqual(self.oauth_calls, [])

    def test_owner_read_only_token_file_is_supported(self):
        self.path.chmod(0o400)
        google = google_fixture.FakeGoogle(google_fixture.purchase())
        self.assertTrue(self.lookup(opener=google)["google_play_lookup_verified"])
        self.assertEqual([method for method, _ in google.requests], ["GET"])

    def test_cli_disabled_and_configured_exit_codes_keep_json_non_sensitive(self):
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main([], environ={})
        self.assertEqual(exit_code, 2)
        self.assertEqual(json.loads(output.getvalue())["state"], "DISABLED")
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main([], environ=self.env, runtime_builder=self.builder)
        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(output.getvalue())["state"], "CONFIGURED")
        self.assertNotIn(self.oauth_value, output.getvalue())


if __name__ == "__main__":
    unittest.main()
