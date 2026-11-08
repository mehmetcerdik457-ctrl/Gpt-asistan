"""Offline regression tests for the isolated Stripe webhook bridge."""
import hashlib
import hmac
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from server.stripe_billing import BillingError, connect_db, process_event, can_access

SECRET = "whsec_example_testing_only"
NOW = 1794182400


def event(event_id="evt_123", event_type="customer.subscription.created", status="active", created=NOW, live=False):
    return {"id":event_id, "type":event_type, "created":created, "livemode":live,
            "data":{"object":{"id":"sub_123", "customer":"cus_123",
                              "status":status, "cancel_at_period_end":False}}}


def sign(payload, stamp=NOW, secret=SECRET):
    digest = hmac.new(secret.encode(), str(stamp).encode() + b"." + payload,
                      hashlib.sha256).hexdigest()
    return f"t={stamp},v1={digest}"


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = connect_db(str(Path(self.temp.name) / "billing.sqlite3"))
        self.env = patch.dict(os.environ, {"STRIPE_LIVEMODE":"false"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.db.close()
        self.temp.cleanup()

    def feed(self, item, header=None):
        payload = json.dumps(item, separators=(",", ":")).encode()
        return process_event(self.db, payload, header or sign(payload), SECRET, now=NOW)

    def test_active_and_duplicate(self):
        x = event()
        self.assertFalse(self.feed(x)["duplicate"])
        self.assertTrue(can_access(self.db, "sub_123"))
        self.assertTrue(self.feed(x)["duplicate"])

    def test_failure_revokes(self):
        self.feed(event())
        self.feed(event("evt_124", "customer.subscription.updated", "past_due", NOW+1))
        self.assertFalse(can_access(self.db, "sub_123"))

    def test_out_of_order_ignored(self):
        self.feed(event("evt_latest", "customer.subscription.updated", "canceled", NOW+3))
        self.feed(event("evt_old", "customer.subscription.created", "active", NOW))
        self.assertFalse(can_access(self.db, "sub_123"))

    def test_invalid_signature(self):
        x = event()
        p = json.dumps(x).encode()
        with self.assertRaises(BillingError):
            process_event(self.db, p, sign(p, secret="whsec_wrong"), SECRET, now=NOW)

    def test_expired_signature(self):
        x = event()
        p = json.dumps(x).encode()
        with self.assertRaises(BillingError):
            process_event(self.db, p, sign(p, NOW-301), SECRET, now=NOW)

    def test_mode_mismatch(self):
        with self.assertRaises(BillingError):
            self.feed(event(live=True))

    def test_invoice_never_grants_access(self):
        x = event(event_type="invoice.paid")
        x["data"]["object"] = {"id":"in_123", "customer":"cus_123", "subscription":"sub_123"}
        self.feed(x)
        self.assertFalse(can_access(self.db, "sub_123"))

    def test_bad_customer_rejected(self):
        x = event()
        x["data"]["object"]["customer"] = "not_cus"
        with self.assertRaises(BillingError):
            self.feed(x)

    def test_missing_signature(self):
        x = event()
        p = json.dumps(x).encode()
        with self.assertRaises(BillingError):
            process_event(self.db, p, "", SECRET, now=NOW)

    def test_deleted_event_revokes(self):
        self.feed(event())
        self.feed(event("evt_125", "customer.subscription.deleted", "active", NOW+1))
        self.assertFalse(can_access(self.db, "sub_123"))


if __name__ == "__main__":
    unittest.main()
