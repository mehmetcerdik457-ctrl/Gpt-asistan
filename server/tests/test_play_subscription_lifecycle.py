"""Google Play subscription lifecycle: explicit benefits and denial boundaries."""
import unittest
from server.play_subscription_lifecycle import access_phase

NOW = 1794000000000


class SubscriptionLifecycleTests(unittest.TestCase):
    def phase(self, state, expiry=NOW + 10_000, now=NOW):
        return access_phase(state, expiry, now)

    def test_active_is_entitled_until_expiry(self):
        self.assertEqual(self.phase("SUBSCRIPTION_STATE_ACTIVE"), "ACTIVE")

    def test_grace_period_retains_benefit(self):
        self.assertEqual(self.phase("SUBSCRIPTION_STATE_IN_GRACE_PERIOD"),
                         "GRACE_PERIOD")

    def test_cancellation_is_paid_through_expiry(self):
        self.assertEqual(self.phase("SUBSCRIPTION_STATE_CANCELED"),
                         "CANCELED_PAID_THROUGH_EXPIRY")

    def test_cancellation_exact_expiry_denied(self):
        self.assertEqual(self.phase("SUBSCRIPTION_STATE_CANCELED", expiry=NOW), "DENIED")

    def test_cancel_after_expiry_denied(self):
        self.assertEqual(self.phase("SUBSCRIPTION_STATE_CANCELED", expiry=NOW - 1), "DENIED")

    def test_grace_exact_expiry_denied(self):
        self.assertEqual(self.phase("SUBSCRIPTION_STATE_IN_GRACE_PERIOD", expiry=NOW), "DENIED")

    def test_active_exact_expiry_denied(self):
        self.assertEqual(self.phase("SUBSCRIPTION_STATE_ACTIVE", expiry=NOW), "DENIED")

    def test_account_hold_denied_even_if_expiry_future(self):
        self.assertEqual(self.phase("SUBSCRIPTION_STATE_ON_HOLD"), "DENIED")

    def test_paused_denied_even_if_expiry_future(self):
        self.assertEqual(self.phase("SUBSCRIPTION_STATE_PAUSED"), "DENIED")

    def test_revoked_or_expired_denied(self):
        self.assertEqual(self.phase("SUBSCRIPTION_STATE_EXPIRED"), "DENIED")

    def test_pending_payment_denied(self):
        self.assertEqual(self.phase("SUBSCRIPTION_STATE_PENDING"), "DENIED")

    def test_pending_purchase_canceled_denied(self):
        self.assertEqual(self.phase("SUBSCRIPTION_STATE_PENDING_PURCHASE_CANCELED"), "DENIED")

    def test_unspecified_denied(self):
        self.assertEqual(self.phase("SUBSCRIPTION_STATE_UNSPECIFIED"), "DENIED")

    def test_unknown_state_denied(self):
        self.assertEqual(self.phase("UNKNOWN"), "DENIED")

    def test_bool_expiry_does_not_count_as_int(self):
        self.assertEqual(self.phase("SUBSCRIPTION_STATE_ACTIVE", expiry=True), "DENIED")

    def test_bool_now_does_not_count_as_int(self):
        self.assertEqual(self.phase("SUBSCRIPTION_STATE_ACTIVE", now=True), "DENIED")

    def test_float_now_denied(self):
        self.assertEqual(self.phase("SUBSCRIPTION_STATE_ACTIVE", now=float(NOW)), "DENIED")

    def test_negative_now_denied(self):
        self.assertEqual(self.phase("SUBSCRIPTION_STATE_ACTIVE", now=-1), "DENIED")

    def test_untrusted_state_dict_denied(self):
        self.assertEqual(self.phase({"subscriptionState": "SUBSCRIPTION_STATE_ACTIVE"}), "DENIED")

    def test_future_expiry_does_not_extend_denied_account_hold(self):
        self.assertEqual(self.phase("SUBSCRIPTION_STATE_ON_HOLD", expiry=NOW+100000), "DENIED")

    def test_no_stale_approval_after_time_advances(self):
        state = "SUBSCRIPTION_STATE_CANCELED"
        self.assertNotEqual(self.phase(state, expiry=NOW+1, now=NOW), "DENIED")
        self.assertEqual(self.phase(state, expiry=NOW+1, now=NOW+1), "DENIED")


if __name__ == "__main__":
    unittest.main()
