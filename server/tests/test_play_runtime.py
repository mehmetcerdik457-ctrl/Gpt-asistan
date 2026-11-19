"""Offline runtime provisioning tests; never connect, fetch Google, or load ADC."""
import base64
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch, sentinel

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from server import play_runtime as runtime
from server.play_entitlement_gate import PACKAGE


def encoded(value):
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def public_der(key):
    return key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


class PlayRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owner_der = public_der(ec.generate_private_key(ec.SECP256R1()))
        cls.device_der = public_der(ec.generate_private_key(ec.SECP256R1()))

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.connector = Mock(return_value=sentinel.connection)
        self.oauth = Mock(return_value="synthetic-access-token")
        self.oauth_factory = Mock(return_value=self.oauth)

    def config(self, *, boundary=False, rtdn=True):
        env = {
            "ORBA_PLAY_BOUNDARY_ENABLED": "YES" if boundary else "NO",
            "ORBA_PLAY_RTDN_ENABLED": "YES" if rtdn else "NO",
            "ORBA_PLAY_OAUTH_ENABLED": "YES",
            "ORBA_PLAY_DATABASE_DSN":
                "postgresql://runtime_user:synthetic-private-password@127.0.0.1/orba_runtime",
            "ORBA_PLAY_PUBLISHER_SERVICE_ACCOUNT":
                "publisher@orba-test.iam.gserviceaccount.com",
            "ORBA_PLAY_PRODUCTS": "orba_pro_monthly,orba_pro_yearly",
            "ORBA_PLAY_PACKAGE": PACKAGE,
            "ORBA_PLAY_SERVER_SECRET_B64": encoded(b"offline-synthetic-server-secret-32bytes"),
            "ORBA_PLAY_PUBSUB_AUDIENCE": "https://push.example.test/api/v1/play/rtdn",
            "ORBA_PLAY_PUBSUB_SERVICE_ACCOUNT": "push@orba-test.iam.gserviceaccount.com",
            "ORBA_PLAY_PUBSUB_SUBSCRIPTION": "projects/orba-test/subscriptions/orba-rtdn",
        }
        if boundary:
            env.update({
                "OMEGA_OWNER_ID": "alice",
                "OMEGA_DEVICE_ID": hashlib.sha256(self.device_der).hexdigest(),
                "OMEGA_OWNER_PUBLIC_DER_B64": encoded(self.owner_der),
                "OMEGA_DEVICE_PUBLIC_DER_B64": encoded(self.device_der),
                "OMEGA_NONCE_DB": str(self.root / "nonces.sqlite3"),
            })
        return env

    def build(self, env):
        return runtime.build_play_runtime(
            env, connect_factory=self.connector, oauth_factory=self.oauth_factory)

    def rejected(self, env, field=None):
        with self.assertRaises(runtime.RuntimeConfigurationError) as caught:
            self.build(env)
        if field:
            self.assertIn(field, caught.exception.fields)
        self.connector.assert_not_called()
        self.oauth_factory.assert_not_called()
        self.oauth.assert_not_called()
        return caught.exception

    def test_default_disabled_never_imports_postgres_or_constructs_oauth(self):
        with patch.dict(sys.modules, {"psycopg": None, "psycopg.conninfo": None}), \
                patch.dict(os.environ, {"PGHOSTADDR": "irrelevant-while-disabled"}):
            result = self.build({})
        self.assertIsNone(result.play_boundary)
        self.assertIsNone(result.rtdn_processor)
        self.connector.assert_not_called()
        self.oauth_factory.assert_not_called()

    def test_omitted_environ_uses_process_environment_and_is_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            result = runtime.build_play_runtime()
        self.assertIsNone(result.play_boundary)
        self.assertIsNone(result.rtdn_processor)

    def test_explicit_no_flags_leave_unprovisioned_runtime_disabled(self):
        result = self.build({"ORBA_PLAY_BOUNDARY_ENABLED": "NO",
                             "ORBA_PLAY_RTDN_ENABLED": "NO",
                             "ORBA_PLAY_OAUTH_ENABLED": "NO"})
        self.assertEqual(result, runtime.PlayRuntime())
        self.oauth_factory.assert_not_called()

    def test_misspelled_flags_fail_configuration_instead_of_silently_activating(self):
        for flag in runtime._FLAGS:
            for value in ("yes", "true", "1", "", True, " YES"):
                with self.subTest(flag=flag, value=value):
                    self.rejected({flag: value}, flag)

    def test_each_feature_requires_explicit_oauth_opt_in(self):
        for feature in ("ORBA_PLAY_BOUNDARY_ENABLED", "ORBA_PLAY_RTDN_ENABLED"):
            with self.subTest(feature=feature):
                self.rejected({feature: "YES"}, "ORBA_PLAY_OAUTH_ENABLED")

    def test_incomplete_config_reports_missing_names_without_values_or_adc(self):
        env = {"ORBA_PLAY_RTDN_ENABLED": "YES", "ORBA_PLAY_OAUTH_ENABLED": "YES",
               "ORBA_PLAY_DATABASE_DSN": "postgresql://sensitive:PRIVATE_DSN@host/db"}
        error = self.rejected(env, "ORBA_PLAY_PUBLISHER_SERVICE_ACCOUNT")
        self.assertEqual(error.code, "PLAY_RUNTIME_CONFIGURATION_MISSING")
        self.assertNotIn("PRIVATE_DSN", str(error))

    def test_rtdn_requires_complete_pubsub_configuration_before_oauth_construction(self):
        for name in runtime._PUBSUB:
            with self.subTest(field=name):
                env = self.config()
                del env[name]
                self.rejected(env, name)

    def test_rtdn_only_builds_without_owner_keys_or_database_connection(self):
        result = self.build(self.config())
        self.assertIsNone(result.play_boundary)
        self.assertIsNotNone(result.rtdn_processor)
        self.assertEqual(result.rtdn_processor.store.schema, "orba")
        self.connector.assert_not_called()
        self.oauth.assert_not_called()
        self.oauth_factory.assert_called_once()
        self.assertEqual(self.oauth_factory.call_args.kwargs["service_account_email"],
                         "publisher@orba-test.iam.gserviceaccount.com")

    def test_both_features_share_one_postgres_store_and_one_oauth_supplier(self):
        env = self.config(boundary=True)
        env["ORBA_PLAY_DATABASE_SCHEMA"] = "orba_runtime"
        with patch("server.play_rtdn_postgres.initialize_postgres_rtdn") as migrate:
            result = self.build(env)
        self.assertIs(result.play_boundary._store, result.rtdn_processor.store)
        self.assertIs(result.play_boundary._oauth, result.rtdn_processor.oauth_supplier)
        self.assertIs(result.play_boundary._oauth, self.oauth)
        self.assertEqual(result.rtdn_processor.store.schema, "orba_runtime")
        self.assertEqual(result.rtdn_processor.snapshot_recorder.keywords,
                         {"schema": "orba_runtime"})
        self.assertEqual(result.play_boundary._products,
                         frozenset(("orba_pro_monthly", "orba_pro_yearly")))
        self.assertEqual(list(self.root.iterdir()), [])
        self.connector.assert_not_called()
        self.oauth.assert_not_called()
        migrate.assert_not_called()

    def test_boundary_only_needs_owner_identity_but_not_pubsub_configuration(self):
        env = self.config(boundary=True, rtdn=False)
        for name in runtime._PUBSUB:
            del env[name]
        result = self.build(env)
        self.assertIsNotNone(result.play_boundary)
        self.assertIsNone(result.rtdn_processor)
        self.connector.assert_not_called()

    def test_lazy_connector_receives_bounded_timeout_and_autocommit(self):
        env = self.config()
        result = self.build(env)
        self.connector.assert_not_called()
        self.assertIs(result.rtdn_processor.store.db_factory(), sentinel.connection)
        self.connector.assert_called_once_with(
            env["ORBA_PLAY_DATABASE_DSN"], autocommit=True, connect_timeout=5)

    def test_ambient_and_supplied_libpq_target_selectors_are_rejected_before_factories(self):
        for name in runtime._PG_SELECTORS:
            for origin in ("ambient", "supplied"):
                with self.subTest(field=name, origin=origin):
                    env = self.config()
                    if origin == "supplied":
                        env[name] = "PRIVATE_TARGET_OVERRIDE"
                    ambient = {name: "PRIVATE_TARGET_OVERRIDE"} if origin == "ambient" else {}
                    with patch.dict(os.environ, ambient):
                        error = self.rejected(env, name)
                    self.assertEqual(error.code, "PLAY_RUNTIME_DATABASE_ENVIRONMENT_CONFLICT")
                    self.assertNotIn("PRIVATE_TARGET_OVERRIDE", str(error))

    def test_postbuild_libpq_environment_mutation_is_rejected_before_connect(self):
        env = self.config()
        result = self.build(env)
        with patch.dict(os.environ, {"PGHOSTADDR": "PRIVATE_AMBIENT_REDIRECTION"}):
            with self.assertRaises(runtime.RuntimeConfigurationError) as caught:
                result.rtdn_processor.store.db_factory()
        self.assertEqual(caught.exception.fields, ("PGHOSTADDR",))
        env["PGOPTIONS"] = "PRIVATE_STARTUP_OPTIONS"
        with self.assertRaises(runtime.RuntimeConfigurationError) as caught:
            result.rtdn_processor.store.db_factory()
        self.assertEqual(caught.exception.fields, ("PGOPTIONS",))
        self.assertNotIn("PRIVATE", str(caught.exception))
        self.connector.assert_not_called()
        self.oauth.assert_not_called()

    def test_default_oauth_is_lazy_and_its_enable_check_observes_revocation(self):
        env = self.config()
        with patch("server.play_google_oauth._default_loader") as load_adc:
            result = runtime.build_play_runtime(env, connect_factory=self.connector)
        oauth = result.rtdn_processor.oauth_supplier
        self.assertTrue(oauth._enabled())
        env["ORBA_PLAY_OAUTH_ENABLED"] = "NO"
        self.assertFalse(oauth._enabled())
        with self.assertRaisesRegex(RuntimeError, "PUBLISHER_OAUTH_DISABLED"):
            oauth()
        load_adc.assert_not_called()
        self.connector.assert_not_called()

    def test_products_reject_empty_duplicate_whitespace_and_invalid_identifiers(self):
        for value in ("", "monthly,", "monthly,monthly", "monthly, yearly", "a/b", "x" * 101):
            with self.subTest(value=value):
                env = self.config()
                env["ORBA_PLAY_PRODUCTS"] = value
                self.rejected(env, "ORBA_PLAY_PRODUCTS")

    def test_package_must_match_server_package(self):
        env = self.config()
        env["ORBA_PLAY_PACKAGE"] = "com.unowned.private.package"
        self.rejected(env, "ORBA_PLAY_PACKAGE")

    def test_schema_rejects_sql_punctuation_and_system_names(self):
        for value in ("", "orba;DROP SCHEMA public", "UpperCase", "pg_catalog", "information_schema"):
            with self.subTest(value=value):
                env = self.config()
                env["ORBA_PLAY_DATABASE_SCHEMA"] = value
                self.rejected(env, "ORBA_PLAY_DATABASE_SCHEMA")

    def test_secret_requires_canonical_urlsafe_base64_of_at_least_32_bytes(self):
        for value in ("PRIVATE_INVALID$VALUE", encoded(b"short"), "A" * 43 + " ",
                      encoded(b"x" * 32)[:-1] + "B", "a" * 9000):
            with self.subTest(size=len(value)):
                env = self.config()
                env["ORBA_PLAY_SERVER_SECRET_B64"] = value
                error = self.rejected(env, "ORBA_PLAY_SERVER_SECRET_B64")
                self.assertNotIn(value, str(error))

    def test_publisher_requires_google_service_account_identity(self):
        env = self.config()
        env["ORBA_PLAY_PUBLISHER_SERVICE_ACCOUNT"] = "private@example.test"
        self.rejected(env, "ORBA_PLAY_PUBLISHER_SERVICE_ACCOUNT")

    def test_pubsub_requires_valid_https_audience_account_and_subscription(self):
        cases = (
            ("ORBA_PLAY_PUBSUB_AUDIENCE", "http://push.example.test/path"),
            ("ORBA_PLAY_PUBSUB_AUDIENCE", "https://user:PRIVATE@push.example.test/path"),
            ("ORBA_PLAY_PUBSUB_AUDIENCE", "https://push.example.test/path#fragment"),
            ("ORBA_PLAY_PUBSUB_AUDIENCE", "https://bad%20host/path"),
            ("ORBA_PLAY_PUBSUB_SERVICE_ACCOUNT", "owner@gmail.com"),
            ("ORBA_PLAY_PUBSUB_SUBSCRIPTION", "projects//subscriptions/test"),
        )
        for name, value in cases:
            with self.subTest(field=name, value=value):
                env = self.config()
                env[name] = value
                self.rejected(env, name)

    def test_dsn_rejects_nonpostgres_ambient_service_multihost_and_startup_options(self):
        values = (
            "sqlite:///tmp/private.sqlite3", "postgresql://user:PRIVATE@127.0.0.1",
            "dbname=orba_runtime user=alice", "service=PRIVATE_SERVICE",
            "host=127.0.0.1 dbname=orba_runtime user=alice service=PRIVATE",
            "host=127.0.0.1,127.0.0.2 dbname=orba_runtime user=alice",
            "host=127.0.0.1 hostaddr=127.0.0.2 dbname=orba_runtime user=alice",
            "host=127.0.0.1 dbname=orba_runtime user=alice options='-c search_path=public'",
            "postgresql://alice:PRIVATE@127.0.0.1:99999/orba_runtime",
            "postgresql://alice:PRIVATE@127.0.0.1/orba_runtime\n",
            "postgresql://alice:PRIVATE%0A@127.0.0.1/orba_runtime",
        )
        for value in values:
            with self.subTest(value=value):
                env = self.config()
                env["ORBA_PLAY_DATABASE_DSN"] = value
                error = self.rejected(env, "ORBA_PLAY_DATABASE_DSN")
                self.assertNotIn("PRIVATE", str(error))

    def test_nonloopback_database_requires_explicit_tls(self):
        for suffix in ("", "?sslmode=disable", "?sslmode=require", "?sslmode=verify-ca"):
            with self.subTest(suffix=suffix):
                env = self.config()
                env["ORBA_PLAY_DATABASE_DSN"] = "postgresql://alice:PRIVATE@db.example.test/orba" + suffix
                self.rejected(env, "ORBA_PLAY_DATABASE_DSN")
        env["ORBA_PLAY_DATABASE_DSN"] = "postgresql://alice:PRIVATE@db.example.test/orba?sslmode=verify-full"
        self.assertIsNotNone(self.build(env).rtdn_processor)
        self.connector.assert_not_called()

    def test_boundary_requires_all_owner_provisioning_fields(self):
        for name in runtime._OWNER:
            with self.subTest(field=name):
                env = self.config(boundary=True)
                del env[name]
                self.rejected(env, name)

    def test_boundary_rejects_bad_keys_same_key_and_wrong_device_fingerprint(self):
        wrong_curve = public_der(ec.generate_private_key(ec.SECP384R1()))
        cases = (
            {"OMEGA_OWNER_PUBLIC_DER_B64": "PRIVATE_BAD_KEY"},
            {"OMEGA_OWNER_PUBLIC_DER_B64": encoded(wrong_curve)},
            {"OMEGA_OWNER_PUBLIC_DER_B64": encoded(self.device_der)},
            {"OMEGA_DEVICE_ID": "0" * 64},
            {"OMEGA_OWNER_ID": "alice/private"},
        )
        for changes in cases:
            with self.subTest(fields=tuple(changes)):
                env = self.config(boundary=True)
                env.update(changes)
                error = self.rejected(env)
                self.assertEqual(error.code, "PLAY_RUNTIME_CONFIGURATION_INVALID")
                self.assertNotIn("PRIVATE_BAD_KEY", str(error))

    def test_nonce_path_requires_absolute_existing_parent_without_creating_files(self):
        for value in ("relative.sqlite3", str(self.root / "missing" / "nonce.sqlite3"),
                      str(self.root), "\0PRIVATE_PATH"):
            with self.subTest(value=value):
                env = self.config(boundary=True)
                env["OMEGA_NONCE_DB"] = value
                self.rejected(env, "OMEGA_NONCE_DB")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_active_missing_optional_postgres_dependency_fails_closed(self):
        with patch.dict(sys.modules, {"psycopg": None, "psycopg.conninfo": None}):
            error = self.rejected(self.config())
        self.assertEqual(error.code, "PLAY_RUNTIME_POSTGRES_DEPENDENCY_MISSING")

    def test_oauth_constructor_failure_does_not_expose_sensitive_exception(self):
        factory = Mock(side_effect=RuntimeError("PRIVATE_ADC_PATH_AND_PASSWORD"))
        with self.assertRaises(runtime.RuntimeConfigurationError) as caught:
            runtime.build_play_runtime(
                self.config(), connect_factory=self.connector, oauth_factory=factory)
        self.assertEqual(str(caught.exception), "PLAY_RUNTIME_INITIALIZATION_FAILED")
        self.connector.assert_not_called()


if __name__ == "__main__":
    unittest.main()
