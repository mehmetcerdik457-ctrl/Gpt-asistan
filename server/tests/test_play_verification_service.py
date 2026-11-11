import json
import sqlite3
import unittest
from copy import deepcopy
from server.play_account_id import obfuscated_play_account_id
from server.play_owner_binding import initialize, OwnershipConflict
from server.play_verification_service import verify_play_entitlement

SECRET = b"offline-only-test-secret-32-bytes-minimum"
NOW = 1794000000000

def provider(owner="alice", state="SUBSCRIPTION_STATE_ACTIVE"):
    return {
        "subscriptionState": state,
        "acknowledgementState": "ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED",
        "externalAccountIdentifiers": {"obfuscatedExternalAccountId":
            obfuscated_play_account_id(authenticated_owner_id=owner, server_secret=SECRET)},
        "lineItems": [{"productId": "orba_pro_monthly", "expiryTime": "2027-01-01T00:00:00Z"}],
    }

def opener(data):
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, size): return json.dumps(data).encode()
    return lambda *_args, **_kwargs: Response()


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        initialize(self.db)
    def tearDown(self): self.db.close()
    def check(self, data, owner="alice", token="token-1"):
        return verify_play_entitlement(
            db=self.db, purchase_token=token, access_token="offline-oauth",
            authenticated_owner_id=owner, product_id="orba_pro_monthly",
            server_secret=SECRET, now_ms=NOW, opener=opener(data))
    def count(self):
        return self.db.execute("SELECT count(*) FROM play_token_owners").fetchone()[0]
    def test_missing_owner_does_not_call_google(self):
        calls = []
        with self.assertRaises(ValueError):
            verify_play_entitlement(
                db=self.db, purchase_token="token-1", access_token="offline-oauth",
                authenticated_owner_id="", product_id="orba_pro_monthly",
                server_secret=SECRET, now_ms=NOW,
                opener=lambda *_a, **_kw: calls.append(1))
        self.assertEqual(calls, [])
        self.assertEqual(self.count(), 0)

    def test_invalid_secret_does_not_call_google(self):
        calls = []
        with self.assertRaises(ValueError):
            verify_play_entitlement(
                db=self.db, purchase_token="token-1", access_token="offline-oauth",
                authenticated_owner_id="alice", product_id="orba_pro_monthly",
                server_secret=b"short", now_ms=NOW,
                opener=lambda *_a, **_kw: calls.append(1))
        self.assertEqual(calls, [])
        self.assertEqual(self.count(), 0)

    def test_invalid_clock_does_not_call_google(self):
        calls = []
        with self.assertRaises(ValueError):
            verify_play_entitlement(
                db=self.db, purchase_token="token-1", access_token="offline-oauth",
                authenticated_owner_id="alice", product_id="orba_pro_monthly",
                server_secret=SECRET, now_ms=True,
                opener=lambda *_a, **_kw: calls.append(1))
        self.assertEqual(calls, [])
        self.assertEqual(self.count(), 0)

    def test_google_network_failure_does_not_bind(self):
        from urllib.error import URLError
        from server.play_google_api import PlayVerificationError
        def broken(*_args, **_kwargs): raise URLError("offline")
        with self.assertRaises(PlayVerificationError):
            verify_play_entitlement(
                db=self.db, purchase_token="token-1", access_token="offline-oauth",
                authenticated_owner_id="alice", product_id="orba_pro_monthly",
                server_secret=SECRET, now_ms=NOW, opener=broken)
        self.assertEqual(self.count(), 0)

    def test_invalid_provider_response_does_not_bind(self):
        from server.play_google_api import PlayVerificationError
        d = provider()
        del d["lineItems"]
        with self.assertRaises(PlayVerificationError):
            self.check(d)
        self.assertEqual(self.count(), 0)

    def test_wrong_product_does_not_bind(self):
        from server.play_subscription_mapper import PlayMappingError
        d = provider()
        d["lineItems"][0]["productId"] = "another_product"
        with self.assertRaises(PlayMappingError):
            self.check(d)
        self.assertEqual(self.count(), 0)

    def test_inactive_state_does_not_bind(self):
        self.assertFalse(self.check(provider(state="SUBSCRIPTION_STATE_ON_HOLD")))
        self.assertEqual(self.count(), 0)

    def test_exact_expiry_boundary_denied_without_binding(self):
        from datetime import datetime, timezone
        d = provider()
        d["lineItems"][0]["expiryTime"] = datetime.fromtimestamp(
            NOW / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        self.assertFalse(self.check(d))
        self.assertEqual(self.count(), 0)

    def test_unacknowledged_active_does_not_bind(self):
        d = provider()
        d["acknowledgementState"] = "ACKNOWLEDGEMENT_STATE_PENDING"
        self.assertFalse(self.check(d))
        self.assertEqual(self.count(), 0)

    def test_canceled_subscription_does_not_bind(self):
        self.assertFalse(self.check(provider(state="SUBSCRIPTION_STATE_CANCELED")))
        self.assertEqual(self.count(), 0)

    def test_verified_active_binds(self):
        self.assertTrue(self.check(provider()))
        self.assertEqual(self.count(), 1)
    def test_repeat_is_idempotent(self):
        self.assertTrue(self.check(provider()))
        self.assertTrue(self.check(provider()))
        self.assertEqual(self.count(), 1)
    def test_pending_does_not_bind(self):
        d = provider(); d["acknowledgementState"] = "ACKNOWLEDGEMENT_STATE_PENDING"
        self.assertFalse(self.check(d))
        self.assertEqual(self.count(), 0)
    def test_expired_does_not_bind(self):
        d = provider(); d["lineItems"][0]["expiryTime"] = "2020-01-01T00:00:00Z"
        self.assertFalse(self.check(d))
        self.assertEqual(self.count(), 0)
    def test_wrong_account_does_not_bind(self):
        from server.play_subscription_mapper import PlayMappingError
        with self.assertRaises(PlayMappingError): self.check(provider(owner="bob"))
        self.assertEqual(self.count(), 0)
    def test_cross_owner_reassignment_rejected(self):
        self.assertTrue(self.check(provider(owner="alice"), owner="alice"))
        with self.assertRaises(OwnershipConflict):
            self.check(provider(owner="bob"), owner="bob")
        self.assertEqual(self.count(), 1)


if __name__ == "__main__": unittest.main()
