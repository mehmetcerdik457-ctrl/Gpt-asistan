import base64
import json
import unittest

from backend.google_play_purchase_verification import (
    PurchaseVerificationError, parse_rtdn_payload, verify_subscription, public_record,
)


class _Request:
    def __init__(self, value):
        self.value = value
    def execute(self):
        return self.value


class _SubscriptionsV2:
    def get(self, **kwargs):
        self.kwargs = kwargs
        return _Request({
            "subscriptionState": "SUBSCRIPTION_STATE_ACTIVE",
            "acknowledgementState": "ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED",
            "latestOrderId": "GPA.test-order",
            "lineItems": [{
                "productId": "pro.monthly",
                "startTime": "2026-11-28T00:00:00Z",
                "expiryTime": "2026-12-28T00:00:00Z",
                "autoRenewingPlan": {"autoRenewEnabled": True},
            }],
        })


class _Purchases:
    def __init__(self):
        self.v2 = _SubscriptionsV2()
    def subscriptionsv2(self):
        return self.v2


class _Publisher:
    def __init__(self):
        self.p = _Purchases()
    def purchases(self):
        return self.p


class PlayVerificationTests(unittest.TestCase):
    def test_rtdn_decode_and_package_binding(self):
        event = {"packageName": "com.example.app", "eventTimeMillis": 123,
                 "subscriptionNotification": {"subscriptionId": "pro.monthly",
                                               "purchaseToken": "secret-token"}}
        envelope = {"message": {"data": base64.b64encode(
            json.dumps(event).encode()).decode(), "messageId": "m1"}}
        parsed = parse_rtdn_payload(envelope, expected_package="com.example.app")
        self.assertEqual(parsed["product_id"], "pro.monthly")
        self.assertNotIn("secret-token", str(parsed["purchase_token_sha256"]))
        with self.assertRaisesRegex(PurchaseVerificationError, "PACKAGE_MISMATCH"):
            parse_rtdn_payload(envelope, expected_package="other.package")

    def test_invalid_payload_fails_closed(self):
        with self.assertRaises(PurchaseVerificationError):
            parse_rtdn_payload({"message": {"data": "%%"}}, expected_package="com.example.app")

    def test_subscription_is_verified_against_publisher_api(self):
        publisher = _Publisher()
        result = verify_subscription(publisher_api=publisher,
            package_name="com.example.app", product_id="pro.monthly",
            purchase_token="secret-token")
        row = public_record(result)
        self.assertEqual(row["purchase_state"], "SUBSCRIPTION_STATE_ACTIVE")
        self.assertTrue(row["auto_renewing"])
        self.assertNotIn("purchase_token", row)
        self.assertEqual(publisher.p.v2.kwargs["token"], "secret-token")


if __name__ == "__main__":
    unittest.main()
