"""No network: post-ack verification and owner binding regression tests."""
import json
import sqlite3
import unittest
import urllib.error
from copy import deepcopy

from server.play_account_id import obfuscated_play_account_id
from server.play_acknowledgement import (
    PlayAcknowledgementError, acknowledge_subscription,
)
from server.play_acknowledgement_service import acknowledge_then_verify_subscription
from server.play_google_api import PlayVerificationError
from server.play_owner_binding import initialize
from server.play_subscription_mapper import PlayMappingError

SECRET = b"offline-only-test-secret-32-bytes-minimum"
NOW = 1794000000000
PRODUCT = "orba_pro_monthly"


def purchase(*, owner="alice", state="SUBSCRIPTION_STATE_ACTIVE",
             ack="ACKNOWLEDGEMENT_STATE_PENDING",
             expiry="2027-01-01T00:00:00Z", product=PRODUCT):
    return {
        "subscriptionState": state,
        "acknowledgementState": ack,
        "externalAccountIdentifiers": {
            "obfuscatedExternalAccountId": obfuscated_play_account_id(
                authenticated_owner_id=owner, server_secret=SECRET)},
        "lineItems": [{"productId": product, "expiryTime": expiry}],
    }


class FakeResponse:
    status = 200

    def __init__(self, data, status=200):
        self.data, self.status = data, status

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def read(self, n):
        return self.data[:n]


class FakeGoogle:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, timeout):
        assert timeout == 8
        self.requests.append((request.get_method(), request.full_url))
        if not self.responses:
            raise AssertionError("UNEXPECTED_GOOGLE_API_CALL")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, dict):
            return FakeResponse(json.dumps(item).encode())
        if isinstance(item, int):
            return FakeResponse(b"", item)
        return FakeResponse(item)


class Tests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        initialize(self.db)

    def tearDown(self):
        self.db.close()

    def rows(self):
        return self.db.execute("SELECT COUNT(*) FROM play_token_owners").fetchone()[0]

    def call(self, google, *, owner="alice", token="purchase-token-1",
             product=PRODUCT, secret=SECRET, now=NOW):
        return acknowledge_then_verify_subscription(
            db=self.db, purchase_token=token, access_token="offline-oauth",
            authenticated_owner_id=owner, product_id=product,
            server_secret=secret, now_ms=now, opener=google,
        )

    def test_pending_ack_is_verified_again_before_grant(self):
        google = FakeGoogle(purchase(), 200,
                            purchase(ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        self.assertTrue(self.call(google))
        self.assertEqual([x[0] for x in google.requests], ["GET", "POST", "GET"])
        self.assertIn("/purchases/subscriptions/orba_pro_monthly/tokens/", google.requests[1][1])
        self.assertTrue(google.requests[1][1].endswith(":acknowledge"))
        self.assertEqual(self.rows(), 1)

    def test_already_acknowledged_no_write_to_google(self):
        google = FakeGoogle(purchase(ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        self.assertTrue(self.call(google))
        self.assertEqual([x[0] for x in google.requests], ["GET"])
        self.assertEqual(self.rows(), 1)

    def test_ack_http_success_without_provider_confirmation_denied(self):
        google = FakeGoogle(purchase(), 200, purchase())
        self.assertFalse(self.call(google))
        self.assertEqual(self.rows(), 0)

    def test_pending_payment_denied_without_ack_call(self):
        google = FakeGoogle(purchase(state="SUBSCRIPTION_STATE_PENDING"))
        self.assertFalse(self.call(google))
        self.assertEqual(len(google.requests), 1)
        self.assertEqual(self.rows(), 0)

    def test_expired_purchase_denied_without_ack_call(self):
        google = FakeGoogle(purchase(expiry="2020-01-01T00:00:00Z"))
        self.assertFalse(self.call(google))
        self.assertEqual(len(google.requests), 1)
        self.assertEqual(self.rows(), 0)

    def test_wrong_owner_refused_before_ack(self):
        google = FakeGoogle(purchase(owner="bob"))
        with self.assertRaises(PlayMappingError):
            self.call(google)
        self.assertEqual(len(google.requests), 1)
        self.assertEqual(self.rows(), 0)

    def test_wrong_product_refused_before_ack(self):
        google = FakeGoogle(purchase(product="orba_different"))
        with self.assertRaises(PlayMappingError):
            self.call(google)
        self.assertEqual(len(google.requests), 1)
        self.assertEqual(self.rows(), 0)

    def test_ack_denied_does_not_bind(self):
        google = FakeGoogle(purchase(), 403)
        with self.assertRaises(PlayAcknowledgementError):
            self.call(google)
        self.assertEqual(self.rows(), 0)

    def test_ack_network_error_does_not_bind(self):
        google = FakeGoogle(purchase(), urllib.error.URLError("offline"))
        with self.assertRaises(PlayAcknowledgementError):
            self.call(google)
        self.assertEqual(self.rows(), 0)

    def test_refresh_network_error_does_not_bind(self):
        google = FakeGoogle(purchase(), 200, urllib.error.URLError("offline"))
        with self.assertRaises(PlayVerificationError):
            self.call(google)
        self.assertEqual(self.rows(), 0)

    def test_post_ack_product_change_denied(self):
        google = FakeGoogle(purchase(), 200,
                            purchase(ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED",
                                     product="orba_different"))
        with self.assertRaises(PlayMappingError):
            self.call(google)
        self.assertEqual(self.rows(), 0)

    def test_post_ack_owner_change_denied(self):
        google = FakeGoogle(purchase(), 200,
                            purchase(ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED",
                                     owner="bob"))
        with self.assertRaises(PlayMappingError):
            self.call(google)
        self.assertEqual(self.rows(), 0)

    def test_repeated_purchase_idempotent_binding(self):
        g1 = FakeGoogle(purchase(), 200,
                        purchase(ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        g2 = FakeGoogle(purchase(ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        self.assertTrue(self.call(g1))
        self.assertTrue(self.call(g2))
        self.assertEqual(self.rows(), 1)
        self.assertEqual([x[0] for x in g2.requests], ["GET"])

    def test_invalid_secret_rejected_before_network(self):
        google = FakeGoogle()
        with self.assertRaises(ValueError):
            self.call(google, secret=b"short")
        self.assertEqual(google.requests, [])

    def test_invalid_owner_rejected_before_network(self):
        google = FakeGoogle()
        with self.assertRaises(ValueError):
            self.call(google, owner="")
        self.assertEqual(google.requests, [])

    def test_invalid_timestamp_rejected_before_network(self):
        google = FakeGoogle()
        with self.assertRaises(ValueError):
            self.call(google, now=True)
        self.assertEqual(google.requests, [])

    def test_invalid_ack_input_rejected_without_google(self):
        google = FakeGoogle()
        with self.assertRaises(PlayAcknowledgementError):
            acknowledge_subscription(purchase_token="bad/token",
                                     product_id=PRODUCT, access_token="token",
                                     opener=google)
        self.assertEqual(google.requests, [])

    def test_missing_oauth_rejected_without_google(self):
        google = FakeGoogle()
        with self.assertRaises(PlayAcknowledgementError):
            acknowledge_subscription(purchase_token="test",
                                     product_id=PRODUCT, access_token="",
                                     opener=google)
        self.assertEqual(google.requests, [])

    def test_unspecified_ack_state_denied(self):
        google = FakeGoogle(purchase(ack="ACKNOWLEDGEMENT_STATE_UNSPECIFIED"))
        with self.assertRaises(PlayMappingError):
            self.call(google)
        self.assertEqual(self.rows(), 0)
        self.assertEqual(len(google.requests), 1)

    def test_post_ack_expiry_denied(self):
        google = FakeGoogle(purchase(), 200,
                            purchase(ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED",
                                     expiry="2020-01-01T00:00:00Z"))
        self.assertFalse(self.call(google))
        self.assertEqual(self.rows(), 0)


if __name__ == "__main__":
    unittest.main()
