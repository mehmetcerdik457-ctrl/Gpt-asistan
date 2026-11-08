import hashlib
import hmac
import json
import tempfile
import unittest
from pathlib import Path

from stripe_bridge.billing import (
    BillingError, BillingStore, list_merchant_subscriptions, verify_stripe_signature,
)


def sign(body, secret='whsec_for_testing', now=1_000_000):
    digest = hmac.new(secret.encode(), str(now).encode() + b'.' + body,
                      hashlib.sha256).hexdigest()
    return f't={now},v1={digest}'


def event(event_id='evt_1', kind='customer.subscription.updated', status='active', created=1_000_000):
    return {'id': event_id, 'type': kind, 'created': created,
            'data': {'object': {'id': 'sub_123', 'customer': 'cus_123', 'status': status,
                                'items': {'data': [{'current_period_end': created + 100}]}}}}


class StripeBillingTests(unittest.TestCase):
    def make_store(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        return BillingStore(str(Path(self.temp.name) / 'events.sqlite3'))

    def test_valid_signature_and_payload(self):
        body = json.dumps(event()).encode()
        self.assertEqual(verify_stripe_signature(body, sign(body),
                         'whsec_for_testing', now=1_000_000)['id'], 'evt_1')

    def test_signed_tamper_fails(self):
        body = json.dumps(event()).encode()
        with self.assertRaisesRegex(BillingError, 'signature_mismatch'):
            verify_stripe_signature(body+b'!', sign(body), 'whsec_for_testing', now=1_000_000)

    def test_expired_and_future_signatures_fail(self):
        body = json.dumps(event()).encode()
        for now in (1_000_301, 999_699):
            with self.subTest(now=now), self.assertRaisesRegex(BillingError, 'stale_webhook'):
                verify_stripe_signature(body, sign(body), 'whsec_for_testing', now=now)

    def test_missing_secret_fails_closed(self):
        body = json.dumps(event()).encode()
        with self.assertRaisesRegex(BillingError, 'webhook_not_configured'):
            verify_stripe_signature(body, sign(body), '', now=1_000_000)

    def test_event_idempotent_and_ordered(self):
        store = self.make_store()
        newer = event('evt_new', 'customer.subscription.updated', 'active', 120)
        older = event('evt_old', 'customer.subscription.updated', 'past_due', 100)
        self.assertEqual(store.accept(newer), 'recorded')
        self.assertEqual(store.accept(newer), 'duplicate')
        self.assertEqual(store.accept(older), 'recorded')
        with store.connect() as db:
            self.assertEqual(db.execute('select status,period_end from stripe_subscriptions').fetchone(),
                             ('active', 220))
            self.assertEqual(db.execute('select count(*) from stripe_events').fetchone()[0], 2)

    def test_invoice_paid_not_entitlement(self):
        store = self.make_store()
        self.assertEqual(store.accept({'id': 'evt_paid', 'type': 'invoice.paid', 'created': 100,
                         'data': {'object': {'id': 'in_1', 'subscription': 'sub_123'}}}), 'recorded')
        with store.connect() as db:
            self.assertEqual(db.execute('select count(*) from stripe_subscriptions').fetchone()[0], 0)

    def test_deleted_cancels(self):
        store = self.make_store()
        self.assertEqual(store.accept(event('evt_2', 'customer.subscription.deleted', 'active', 120)),
                         'recorded')
        with store.connect() as db:
            self.assertEqual(db.execute('select status from stripe_subscriptions').fetchone()[0], 'canceled')

    def test_invalid_subscription_identity_fails(self):
        store = self.make_store()
        e = event()
        e['data']['object']['customer'] = 'not an id!!'
        with self.assertRaisesRegex(BillingError, 'invalid_subscription_identity'):
            store.accept(e)

    def test_no_client_side_or_unscoped_keys(self):
        with self.assertRaisesRegex(BillingError, 'server_side_stripe_key_required'):
            list_merchant_subscriptions('pk_test_bad')

    def test_incomplete_event_fails(self):
        store = self.make_store()
        with self.assertRaisesRegex(BillingError, 'missing_event_object'):
            store.accept({'id': 'evt_empty', 'type': 'invoice.paid', 'created': 10, 'data': {}})


if __name__ == '__main__':
    unittest.main()