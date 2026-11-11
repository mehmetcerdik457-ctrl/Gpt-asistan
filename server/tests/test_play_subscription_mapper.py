import unittest
from copy import deepcopy
from server.play_subscription_mapper import map_verified_subscription, PlayMappingError
from server.play_entitlement_gate import entitlement_allowed, token_digest

DATA = {
    "subscriptionState": "SUBSCRIPTION_STATE_ACTIVE",
    "acknowledgementState": "ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED",
    "lineItems": [{"productId": "orba_pro_monthly", "expiryTime": "2027-01-01T00:00:00Z"}],
}
NOW = 1794000000000


class MappingTests(unittest.TestCase):
    def mapping(self, data=None):
        return map_verified_subscription(DATA if data is None else data,
                                         purchase_token="offline-test-token", owner_id="owner-1",
                                         product_id="orba_pro_monthly")

    def allowed(self, mapped):
        return entitlement_allowed(mapped, owner_id="owner-1", product_id="orba_pro_monthly",
                                   token_sha256=token_digest("offline-test-token"), now_ms=NOW)

    def test_active_acknowledged(self): self.assertTrue(self.allowed(self.mapping()))
    def test_pending_acknowledgement_denied(self):
        d = deepcopy(DATA); d["acknowledgementState"] = "ACKNOWLEDGEMENT_STATE_PENDING"
        self.assertFalse(self.allowed(self.mapping(d)))
    def test_expired_denied(self):
        d = deepcopy(DATA); d["lineItems"][0]["expiryTime"] = "2026-01-01T00:00:00Z"
        self.assertFalse(self.allowed(self.mapping(d)))
    def test_wrong_product(self):
        d = deepcopy(DATA); d["lineItems"][0]["productId"] = "other"
        with self.assertRaises(PlayMappingError): self.mapping(d)
    def test_duplicate_product(self):
        d = deepcopy(DATA); d["lineItems"].append(deepcopy(d["lineItems"][0]))
        with self.assertRaises(PlayMappingError): self.mapping(d)
    def test_missing_expiry(self):
        d = deepcopy(DATA); del d["lineItems"][0]["expiryTime"]
        with self.assertRaises(PlayMappingError): self.mapping(d)
    def test_invalid_expiry(self):
        d = deepcopy(DATA); d["lineItems"][0]["expiryTime"] = "not-a-date"
        with self.assertRaises(PlayMappingError): self.mapping(d)
    def test_missing_acknowledgement(self):
        d = deepcopy(DATA); del d["acknowledgementState"]
        with self.assertRaises(PlayMappingError): self.mapping(d)
    def test_cancelled_denied(self):
        d = deepcopy(DATA); d["subscriptionState"] = "SUBSCRIPTION_STATE_CANCELED"
        self.assertFalse(self.allowed(self.mapping(d)))
    def test_invalid_owner(self):
        with self.assertRaises(PlayMappingError):
            map_verified_subscription(DATA, purchase_token="test", owner_id="", product_id="orba_pro_monthly")


if __name__ == "__main__": unittest.main()
