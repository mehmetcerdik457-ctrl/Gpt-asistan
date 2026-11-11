import unittest
from dataclasses import replace
from server.play_entitlement_gate import VerifiedPlayPurchase, entitlement_allowed, token_digest, PACKAGE

TOKEN = token_digest("sandbox-test-token-only")
NOW = 1794000000000


class PlayGateTests(unittest.TestCase):
    def setUp(self):
        self.p = VerifiedPlayPurchase(PACKAGE, "orba_pro_monthly", TOKEN, "owner-1", NOW + 10000,
                                      "SUBSCRIPTION_STATE_ACTIVE", True, True)

    def allowed(self, p=None, **kwargs):
        args = dict(owner_id="owner-1", product_id="orba_pro_monthly", token_sha256=TOKEN, now_ms=NOW)
        args.update(kwargs)
        return entitlement_allowed(self.p if p is None else p, **args)

    def test_verified_active(self): self.assertTrue(self.allowed())
    def test_unverified(self): self.assertFalse(self.allowed(replace(self.p, verified_by_google_api=False)))
    def test_unacknowledged(self): self.assertFalse(self.allowed(replace(self.p, acknowledged=False)))
    def test_wrong_owner(self): self.assertFalse(self.allowed(owner_id="owner-2"))
    def test_wrong_product(self): self.assertFalse(self.allowed(product_id="orba_other"))
    def test_wrong_package(self): self.assertFalse(self.allowed(replace(self.p, package_name="fake.package")))
    def test_wrong_token(self): self.assertFalse(self.allowed(token_sha256=token_digest("other")))
    def test_expired(self): self.assertFalse(self.allowed(now_ms=NOW + 10000))
    def test_cancelled(self): self.assertFalse(self.allowed(replace(self.p, subscription_state="SUBSCRIPTION_STATE_CANCELED")))
    def test_on_hold(self): self.assertFalse(self.allowed(replace(self.p, subscription_state="SUBSCRIPTION_STATE_ON_HOLD")))
    def test_pending(self): self.assertFalse(self.allowed(replace(self.p, subscription_state="SUBSCRIPTION_STATE_PENDING")))
    def test_bad_hash(self): self.assertFalse(self.allowed(token_sha256="bad"))
    def test_untrusted_dict(self): self.assertFalse(self.allowed(self.p.__dict__))
    def test_bad_time(self): self.assertFalse(self.allowed(now_ms=True))
    def test_invalid_token(self):
        with self.assertRaises(ValueError): token_digest("")


if __name__ == "__main__":
    unittest.main()
