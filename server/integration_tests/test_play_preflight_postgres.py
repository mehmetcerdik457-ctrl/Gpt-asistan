"""Read-only readiness checks against a real disposable PostgreSQL database.

The fixture creates a random least-privileged runtime role with a generated
test password. Only this test's random schema and role are removed on exit.
No Google credentials, remote database, production schema or writes by the
preflight itself are used.
"""
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
import psycopg
import secrets
from types import SimpleNamespace
import unittest
import uuid

from server.play_preflight import preflight
from server.play_runtime import PlayRuntime
from server.integration_tests import test_play_rtdn_postgres as postgres_fixture
from server.tests import test_play_acknowledgement_service as google_fixture


class PostgresPreflightTests(unittest.TestCase):
    def setUp(self):
        self.role = None
        self.owner_roles = []
        # Cleanups are LIFO: remove schema grants before dropping the role.
        self.addCleanup(self.drop_role)
        self.pg = postgres_fixture.PostgresRtdnTests(
            methodName="test_bound_delivery_commits_snapshot_and_audit")
        self.addCleanup(self.pg.doCleanups)
        self.pg.setUp()
        self.role = "orba_preflight_" + uuid.uuid4().hex
        self.password = secrets.token_hex(24)
        with self.pg.connect() as connection:
            connection.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB "
                "NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}").format(
                    sql.Identifier(self.role), sql.Literal(self.password)))
            connection.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                sql.Identifier(self.pg.schema), sql.Identifier(self.role)))
            for table, permissions in (
                ("play_token_owners", "SELECT, INSERT, UPDATE"),
                ("play_rtdn_audit", "SELECT, INSERT"),
                ("play_verified_snapshots", "SELECT, INSERT, UPDATE"),
            ):
                connection.execute(sql.SQL("GRANT " + permissions + " ON TABLE {} TO {}").format(
                    sql.Identifier(self.pg.schema, table), sql.Identifier(self.role)))
        self.oauth_calls = []
        self.store = SimpleNamespace(schema=self.pg.schema, db_factory=self.connect)
        self.runtime = PlayRuntime(play_boundary=SimpleNamespace(
            _store=self.store, _oauth=self.forbidden_oauth,
            _products={google_fixture.PRODUCT}, _secret=google_fixture.SECRET))

    def drop_role(self):
        if self.role is not None:
            with self.pg.connect() as connection:
                connection.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(self.role)))
                for owner_role in self.owner_roles:
                    connection.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(owner_role)))

    def connect(self):
        settings = conninfo_to_dict(self.pg.dsn)
        settings.update(user=self.role, password=self.password)
        return psycopg.connect(**settings, autocommit=True, connect_timeout=3)

    def forbidden_oauth(self):
        self.oauth_calls.append(True)
        raise AssertionError("database-only readiness must not request OAuth")

    def check(self):
        return preflight(environ={}, check_database=True,
                         runtime_builder=lambda **_: self.runtime)

    def assert_failure(self, code):
        result = self.check()
        self.assertFalse(result["ok"])
        self.assertEqual(result["checks"]["database"], {"status": "FAILED", "code": code})
        self.assertFalse(result["production_acceptance"])
        self.assertEqual(self.oauth_calls, [])
        self.assertNotIn(self.password, str(result))
        return result

    def test_least_privileged_schema_passes_without_writing_rows_or_calling_google(self):
        self.assertEqual(self.pg.counts(), (0, 0, 0))
        result = self.check()
        self.assertEqual(result["checks"]["database"], {
            "status": "PASS", "code": "DATABASE_READ_ONLY_CHECKS_PASSED"})
        self.assertTrue(result["ok"])
        self.assertFalse(result["production_acceptance"])
        self.assertFalse(result["google_play_lookup_verified"])
        self.assertEqual(self.oauth_calls, [])
        self.assertEqual(self.pg.counts(), (0, 0, 0))

    def test_superuser_runtime_connection_is_rejected(self):
        self.store.db_factory = self.pg.connect
        self.assert_failure("DATABASE_ROLE_TOO_PRIVILEGED")

    def test_schema_create_permission_is_rejected(self):
        with self.pg.connect() as connection:
            connection.execute(sql.SQL("GRANT CREATE ON SCHEMA {} TO {}").format(
                sql.Identifier(self.pg.schema), sql.Identifier(self.role)))
        self.assert_failure("DATABASE_ROLE_CAN_CREATE_SCHEMA_OBJECTS")

    def test_table_owner_is_rejected_even_when_schema_create_is_revoked(self):
        with self.pg.connect() as connection:
            connection.execute(sql.SQL("GRANT CREATE ON SCHEMA {} TO {}").format(
                sql.Identifier(self.pg.schema), sql.Identifier(self.role)))
            connection.execute(sql.SQL("ALTER TABLE {} OWNER TO {}").format(
                sql.Identifier(self.pg.schema, "play_rtdn_audit"), sql.Identifier(self.role)))
            connection.execute(sql.SQL("REVOKE CREATE ON SCHEMA {} FROM {}").format(
                sql.Identifier(self.pg.schema), sql.Identifier(self.role)))
        with self.connect() as connection:
            self.assertFalse(connection.execute(
                "SELECT pg_catalog.has_schema_privilege(current_user,%s,'CREATE')",
                (self.pg.schema,),
            ).fetchone()[0])
        self.assert_failure("DATABASE_ROLE_OWNS_SCHEMA_OR_TABLES")

    def test_member_of_table_owner_role_is_rejected_without_inherited_create(self):
        owner_role = "orba_preflight_owner_" + uuid.uuid4().hex
        self.owner_roles.append(owner_role)
        with self.pg.connect() as connection:
            connection.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB "
                "NOCREATEROLE NOREPLICATION NOBYPASSRLS").format(sql.Identifier(owner_role)))
            connection.execute(sql.SQL("GRANT CREATE ON SCHEMA {} TO {}").format(
                sql.Identifier(self.pg.schema), sql.Identifier(owner_role)))
            connection.execute(sql.SQL("ALTER TABLE {} OWNER TO {}").format(
                sql.Identifier(self.pg.schema, "play_verified_snapshots"), sql.Identifier(owner_role)))
            connection.execute(sql.SQL("REVOKE CREATE ON SCHEMA {} FROM {}").format(
                sql.Identifier(self.pg.schema), sql.Identifier(owner_role)))
            connection.execute(sql.SQL("GRANT {} TO {} WITH INHERIT FALSE, SET TRUE").format(
                sql.Identifier(owner_role), sql.Identifier(self.role)))
        with self.connect() as connection:
            self.assertFalse(connection.execute(
                "SELECT pg_catalog.has_schema_privilege(current_user,%s,'CREATE')",
                (self.pg.schema,),
            ).fetchone()[0])
            self.assertTrue(connection.execute(
                "SELECT pg_catalog.pg_has_role(current_user,%s,'MEMBER')", (owner_role,),
            ).fetchone()[0])
        self.assert_failure("DATABASE_ROLE_OWNS_SCHEMA_OR_TABLES")

    def test_schema_owner_is_rejected_after_its_create_acl_is_revoked(self):
        with self.pg.connect() as connection:
            connection.execute(sql.SQL("ALTER SCHEMA {} OWNER TO {}").format(
                sql.Identifier(self.pg.schema), sql.Identifier(self.role)))
            connection.execute(sql.SQL("REVOKE CREATE ON SCHEMA {} FROM {}").format(
                sql.Identifier(self.pg.schema), sql.Identifier(self.role)))
        with self.connect() as connection:
            self.assertFalse(connection.execute(
                "SELECT pg_catalog.has_schema_privilege(current_user,%s,'CREATE')",
                (self.pg.schema,),
            ).fetchone()[0])
        self.assert_failure("DATABASE_ROLE_OWNS_SCHEMA_OR_TABLES")

    def test_missing_usage_permission_is_rejected(self):
        with self.pg.connect() as connection:
            connection.execute(sql.SQL("REVOKE USAGE ON SCHEMA {} FROM {}").format(
                sql.Identifier(self.pg.schema), sql.Identifier(self.role)))
        self.assert_failure("DATABASE_PERMISSIONS_MISSING")

    def test_missing_success_audit_insert_privilege_is_rejected(self):
        with self.pg.connect() as connection:
            connection.execute(sql.SQL("REVOKE INSERT ON TABLE {} FROM {}").format(
                sql.Identifier(self.pg.schema, "play_rtdn_audit"), sql.Identifier(self.role)))
        self.assert_failure("DATABASE_PERMISSIONS_MISSING")

    def test_missing_snapshot_column_is_rejected_without_migrating_it(self):
        with self.pg.connect() as connection:
            connection.execute(sql.SQL("ALTER TABLE {} DROP COLUMN observed_at_ms").format(
                sql.Identifier(self.pg.schema, "play_verified_snapshots")))
        self.assert_failure("DATABASE_COLUMNS_MISSING")
        with self.pg.connect() as connection:
            columns = connection.execute("""SELECT column_name FROM information_schema.columns
                WHERE table_schema=%s AND table_name='play_verified_snapshots'""",
                (self.pg.schema,)).fetchall()
        self.assertNotIn(("observed_at_ms",), columns)

    def test_missing_audit_table_is_rejected_without_creating_it(self):
        with self.pg.connect() as connection:
            connection.execute(sql.SQL("DROP TABLE {}").format(
                sql.Identifier(self.pg.schema, "play_rtdn_audit")))
        self.assert_failure("DATABASE_TABLES_MISSING")
        with self.pg.connect() as connection:
            found = connection.execute("""SELECT 1 FROM information_schema.tables
                WHERE table_schema=%s AND table_name='play_rtdn_audit'""",
                (self.pg.schema,)).fetchone()
        self.assertIsNone(found)

    def test_missing_primary_key_cannot_pass_idempotency_readiness(self):
        with self.pg.connect() as connection:
            connection.execute(sql.SQL("ALTER TABLE {} DROP CONSTRAINT play_rtdn_audit_pkey").format(
                sql.Identifier(self.pg.schema, "play_rtdn_audit")))
        self.assert_failure("DATABASE_PRIMARY_KEYS_MISSING")

    def test_unmigrated_schema_is_reported_without_ddl(self):
        self.store.schema = self.pg.schema + "_absent"
        self.assert_failure("DATABASE_SCHEMA_MISSING")

    def test_factory_with_existing_transaction_is_rejected(self):
        def busy_connection():
            connection = self.connect()
            connection.execute("BEGIN")
            return connection
        self.store.db_factory = busy_connection
        self.assert_failure("DATABASE_SESSION_NOT_IDLE")


if __name__ == "__main__":
    unittest.main()
