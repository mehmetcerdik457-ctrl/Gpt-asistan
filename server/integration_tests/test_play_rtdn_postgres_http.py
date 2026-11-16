"""Loopback HTTP + real isolated PostgreSQL; Google/OIDC remain synthetic.

Run explicitly with OMEGA_ORBA_TEST_PG_DSN. This module deliberately lives
outside server/tests so offline discovery does not require PostgreSQL.
"""
import json
import os
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from psycopg import sql

from server.gateway import CONTRACT
from server.integration_tests import test_play_rtdn_postgres as postgres_fixture
from server.play_rtdn import ENDPOINT
from server.play_rtdn_postgres import record_postgres_snapshot
from server.tests import test_gateway as gateway_fixture
from server.tests.test_play_acknowledgement_service import FakeGoogle, purchase
from server.tests.test_play_rtdn import JWT, wrapped


class PostgresRtdnHttpTests(unittest.TestCase):
    def setUp(self):
        # Compose the fixtures; do not inherit their test methods or import
        # their TestCase classes into this module's discovery namespace.
        self.pg = postgres_fixture.PostgresRtdnTests(
            methodName="test_bound_delivery_commits_snapshot_and_audit")
        self.addCleanup(self.pg.doCleanups)
        self.pg.setUp()
        self.enterContext(patch.dict(os.environ, {"ORBA_PLAY_RTDN_ENABLED": "YES"}))
        self.http = gateway_fixture.GatewayHttpTests(
            methodName="test_no_provider_calls_without_auth")
        self.http.setUp()
        self.addCleanup(self.http.tearDown)
        self.http.gateway.rtdn_processor = self.pg.processor

    def post(self, raw=None, authorization="Bearer " + JWT):
        request = urllib.request.Request(
            self.http.url + ENDPOINT,
            data=wrapped(msgid="http-delivery-1") if raw is None else raw,
            headers={"Content-Type": "application/json", "Authorization": authorization},
            method="POST",
        )
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def test_authenticated_push_and_new_processor_duplicate_persist_one_google_get(self):
        self.pg.bind()
        self.assertEqual(self.post(), (200, {
            "contract": CONTRACT, "rtdn": "AUDITED", "entitlement_changed": False,
        }))
        self.assertEqual(self.pg.counts(), (1, 1, 1))
        # An independent processor must consult persisted PostgreSQL state.
        self.http.gateway.rtdn_processor = self.pg.make_processor()
        self.assertEqual(self.post(), (200, {
            "contract": CONTRACT, "rtdn": "DUPLICATE", "entitlement_changed": False,
        }))
        self.assertEqual(self.pg.counts(), (1, 1, 1))
        self.assertEqual(self.pg.rows("play_rtdn_audit")[0][3], "RECHECKED_BOUND")
        self.assertEqual(self.pg.rows("play_verified_snapshots")[0][3],
                         "SUBSCRIPTION_STATE_ACTIVE")
        self.assertEqual([method for method, _ in self.pg.google.requests], ["GET"])
        self.assertEqual(self.http.provider.calls, [])

    def test_invalid_oidc_returns_403_before_postgres_factory_or_provider(self):
        factory_calls = []
        verifier_calls = []

        def forbidden_factory():
            factory_calls.append(True)
            raise AssertionError("database factory must not run before authentication")

        def invalid_signature(*_):
            verifier_calls.append(True)
            raise ValueError("PRIVATE_OIDC_SIGNATURE_FAILURE")

        processor = self.pg.make_processor(factory=forbidden_factory)
        processor.verifier = invalid_signature
        self.http.gateway.rtdn_processor = processor
        self.assertEqual(self.post(), (403, {
            "contract": CONTRACT, "error": "RTDN_AUTH_DENIED",
        }))
        self.assertEqual(verifier_calls, [True])
        self.assertEqual(factory_calls, [])
        self.assertEqual(self.pg.google.requests, [])
        self.assertEqual(self.http.provider.calls, [])
        self.assertEqual(self.pg.counts(), (0, 0, 0))

    def test_audit_insert_failure_returns_503_rolls_back_snapshot_and_allows_retry(self):
        self.pg.bind()
        snapshot_writes = []

        def record_and_observe(connection, verified, **kwargs):
            updated = record_postgres_snapshot(
                connection, verified, schema=self.pg.schema, **kwargs)
            snapshot_writes.append(connection.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(
                sql.Identifier(self.pg.schema, "play_verified_snapshots"))).fetchone()[0])
            return updated

        with self.pg.connect() as connection:
            connection.execute(sql.SQL(
                "ALTER TABLE {} ADD CONSTRAINT reject_http_audit CHECK(false) NOT VALID"
            ).format(sql.Identifier(self.pg.schema, "play_rtdn_audit")))
        self.http.gateway.rtdn_processor = self.pg.make_processor(recorder=record_and_observe)
        self.assertEqual(self.post(), (503, {
            "contract": CONTRACT, "error": "RTDN_RETRY_REQUIRED",
        }))
        # The callback really inserted evidence inside the HTTP transaction;
        # a separate backend observes that the failed audit rolled it back.
        self.assertEqual(snapshot_writes, [1])
        self.assertEqual(self.pg.counts(), (0, 0, 1))
        self.assertEqual(len(self.pg.google.requests), 1)
        with self.pg.connect() as connection:
            connection.execute(sql.SQL("ALTER TABLE {} DROP CONSTRAINT reject_http_audit").format(
                sql.Identifier(self.pg.schema, "play_rtdn_audit")))
        self.pg.google = FakeGoogle(purchase(
            owner="alice", ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        self.assertEqual(self.post(), (200, {
            "contract": CONTRACT, "rtdn": "AUDITED", "entitlement_changed": False,
        }))
        self.assertEqual(snapshot_writes, [1, 1])
        self.assertEqual(self.pg.counts(), (1, 1, 1))
        self.assertEqual(len(self.pg.google.requests), 1)
        self.assertEqual(self.http.provider.calls, [])


if __name__ == "__main__":
    unittest.main()
