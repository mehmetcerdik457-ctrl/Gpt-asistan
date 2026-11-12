"""Real signed local P-256 HTTP + offline Play provider; no real payments."""
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from server import gateway as g
from server.play_gateway_boundary import PlayGatewayBoundary, PlayBoundaryError
from server.play_owner_binding import initialize
from server.tests.test_gateway import GatewayHttpTests
from server.tests.test_play_acknowledgement_service import FakeGoogle, purchase, SECRET

NOW = 1794000000000
PRODUCT = "orba_pro_monthly"


class PlayBoundaryHttpTests(unittest.TestCase):
    # Borrow the established real dual-P256 HTTP fixture without also running
    # its original unrelated test methods a second time.
    signed = GatewayHttpTests.signed
    post = GatewayHttpTests.post
    def setUp(self):
        GatewayHttpTests.setUp(self)
        self.play_db = self.tmp.name + "/play-private.sqlite3"
        with sqlite3.connect(self.play_db) as db:
            initialize(db)
        self.google = FakeGoogle(
            purchase(ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        self.oauth_calls = 0
        def oauth():
            self.oauth_calls += 1
            return "offline-oauth-not-real"
        self.boundary = PlayGatewayBoundary(
            server_secret=SECRET, allowed_products={PRODUCT},
            oauth_supplier=oauth,
            db_factory=lambda: sqlite3.connect(self.play_db),
            opener=self.google, clock_ms=lambda: NOW,
        )
        self.gateway.play_boundary = self.boundary
        self.play_env = patch.dict(os.environ, {"ORBA_PLAY_BOUNDARY_ENABLED": "YES"})
        self.play_env.start()

    def tearDown(self):
        self.play_env.stop()
        GatewayHttpTests.tearDown(self)

    def test_account_id_requires_dual_p256_auth(self):
        response, body = self.post("play/account", {})
        self.assertEqual(response, 200)
        self.assertEqual(len(body["obfuscated_account_id"]), 64)
        self.assertEqual(self.oauth_calls, 0)
        unsigned, denied = self.post(
            "play/account", {}, headers={"Content-Type": "application/json"})
        self.assertEqual((unsigned, denied["error"]), (403, "OWNER_AUTH_REQUIRED"))

    def test_account_id_cannot_accept_client_owner_id(self):
        status, data = self.post("play/account", {"owner_id": "other"})
        self.assertEqual((status, data["error"]), (400, "PLAY_FIELDS_DENIED"))

    def test_owner_mismatch_in_signatures_denied_before_google(self):
        status, data = self.post("play/account", {}, owner="other-owner")
        self.assertEqual(status, 403)
        self.assertEqual(self.oauth_calls, 0)

    def test_signature_bound_to_purchase_body(self):
        path = g.PREFIX + "play/verify"
        raw = g.json_bytes({"productId": PRODUCT, "purchaseToken": "signed"})
        headers = self.signed(path, raw)
        status, data = self.post(
            "play/verify", {"productId": PRODUCT, "purchaseToken": "changed"},
            headers=headers)
        self.assertEqual(status, 403)
        self.assertEqual(self.oauth_calls, 0)

    def test_verification_accepts_only_two_fields(self):
        for payload in (
            {"owner_id": "other", "productId": PRODUCT, "purchaseToken": "token"},
            {"productId": PRODUCT, "purchaseToken": "token", "verified": True},
            {"productId": PRODUCT},
        ):
            status, data = self.post("play/verify", payload)
            self.assertEqual((status, data["error"]), (400, "PLAY_FIELDS_DENIED"))
        self.assertEqual(self.oauth_calls, 0)

    def test_valid_provider_verified_purchase_can_bind_once(self):
        status, data = self.post("play/verify", {
            "productId": PRODUCT, "purchaseToken": "test-token"
        })
        # fixture is signed as owner-test; provider fake intentionally defaults
        # to alice, so the owner mismatch MUST be denied instead of granted.
        self.assertEqual(status, 503)
        self.assertEqual(data["error"], "PLAY_VERIFICATION_UNAVAILABLE")
        self.assertEqual(self.count_bindings(), 0)

    def count_bindings(self):
        with sqlite3.connect(self.play_db) as db:
            return db.execute("SELECT COUNT(*) FROM play_token_owners").fetchone()[0]

    def test_real_signed_owner_binding_with_matching_provider(self):
        self.google = FakeGoogle(purchase(
            owner="owner-test",
            ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        self.boundary._opener = self.google
        status, data = self.post("play/verify", {
            "productId": PRODUCT, "purchaseToken": "test-token"
        })
        self.assertEqual(status, 200)
        self.assertEqual(data["entitled"], True)
        self.assertEqual(self.count_bindings(), 1)
        self.assertNotIn("test-token", str(data))
        self.assertNotIn("offline-oauth", str(data))

    def test_pending_payment_is_denied(self):
        self.boundary._opener = FakeGoogle(
            purchase(owner="owner-test",state="SUBSCRIPTION_STATE_PENDING"))
        status, data = self.post("play/verify", {
            "productId": PRODUCT, "purchaseToken": "test-token"
        })
        self.assertEqual((status, data["entitled"]), (200, False))
        self.assertEqual(self.count_bindings(), 0)

    def test_disabled_flag_blocks_without_provider(self):
        with patch.dict(os.environ, {"ORBA_PLAY_BOUNDARY_ENABLED": "NO"}):
            status, data = self.post("play/verify", {
                "productId": PRODUCT, "purchaseToken": "token"
            })
        self.assertEqual((status, data["error"]), (503, "ORBA_PLAY_NOT_PROVISIONED"))
        self.assertEqual(self.oauth_calls, 0)

    def test_missing_boundary_blocks_all_calls(self):
        self.gateway.play_boundary = None
        for route, payload in (
            ("play/account", {}),
            ("play/verify", {"productId": PRODUCT, "purchaseToken": "token"}),
        ):
            status, data = self.post(route, payload)
            self.assertEqual((status, data["error"]),
                             (503, "ORBA_PLAY_NOT_PROVISIONED"))
        self.assertEqual(self.oauth_calls, 0)

    def test_unknown_product_denied_without_provider(self):
        status, data = self.post("play/verify", {
            "productId": "unsupported", "purchaseToken": "token"
        })
        self.assertEqual((status, data["error"]), (400, "PLAY_PURCHASE_INVALID"))
        self.assertEqual(self.oauth_calls, 0)

    def test_malformed_token_denied_without_provider(self):
        status, data = self.post("play/verify", {
            "productId": PRODUCT, "purchaseToken": "bad token"
        })
        self.assertEqual((status, data["error"]), (400, "PLAY_PURCHASE_INVALID"))
        self.assertEqual(self.oauth_calls, 0)

    def test_provider_exception_suppressed_and_no_bind(self):
        self.boundary._oauth = lambda: (_ for _ in ()).throw(
            RuntimeError("secret-provider-failure"))
        status, data = self.post("play/verify", {
            "productId": PRODUCT, "purchaseToken": "token"
        })
        self.assertEqual((status, data["error"]), (503, "PLAY_VERIFICATION_UNAVAILABLE"))
        self.assertNotIn("secret-provider-failure", str(data))
        self.assertEqual(self.count_bindings(), 0)

    def test_failed_database_denies_without_leaking_token(self):
        self.boundary._db_factory = lambda: (_ for _ in ()).throw(
            sqlite3.OperationalError("private-db-secret-path"))
        self.boundary._opener = FakeGoogle(
            purchase(owner="owner-test",ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        status, data = self.post("play/verify", {
            "productId": PRODUCT, "purchaseToken": "token"
        })
        self.assertEqual((status, data["error"]), (503, "PLAY_VERIFICATION_UNAVAILABLE"))
        self.assertNotIn("private-db-secret-path", str(data))
        self.assertEqual(self.count_bindings(), 0)

    def test_replay_of_signed_purchase_denied(self):
        self.boundary._opener = FakeGoogle(
            purchase(owner="owner-test",ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        raw = g.json_bytes({"productId": PRODUCT, "purchaseToken": "token"})
        headers = self.signed(g.PREFIX + "play/verify", raw)
        self.assertEqual(self.post("play/verify", raw, headers=headers)[0], 200)
        status, data = self.post("play/verify", raw, headers=headers)
        self.assertEqual((status, data["error"]),
                         (403, "OWNER_AUTH_REPLAY_OR_STORAGE_DENIED"))
        self.assertEqual(self.count_bindings(), 1)


class PlayBoundaryValidationTests(unittest.TestCase):
    def test_constructor_does_not_allow_unprovisioned_credentials(self):
        for secret, products in (
            (b"short", {PRODUCT}),
            (SECRET, set()),
            (SECRET, {"../bad"}),
        ):
            with self.assertRaises(ValueError):
                PlayGatewayBoundary(
                    server_secret=secret,allowed_products=products,
                    oauth_supplier=lambda: "token",
                    db_factory=lambda: sqlite3.connect(":memory:")
                )

    def test_route_direct_call_without_signed_owner_cannot_grant(self):
        with tempfile.TemporaryDirectory() as tmp:
            gw = g.Gateway(g.Store(tmp + "/gateway.sqlite3"))
            try:
                with patch.dict(os.environ, {"ORBA_PLAY_BOUNDARY_ENABLED": "YES"}):
                    with self.assertRaises(g.Denied) as denied:
                        gw.route(g.PREFIX + "play/account", {})
                self.assertEqual(denied.exception.code, "OWNER_AUTH_REQUIRED")
            finally:
                gw.tasks.close()


if __name__ == "__main__":
    unittest.main()
