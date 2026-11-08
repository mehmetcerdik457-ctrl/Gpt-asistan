import hashlib
import hmac
import json
import sqlite3
import time

import pytest

from stripe_bridge.billing import (
    BillingError, BillingStore, list_merchant_subscriptions, verify_stripe_signature,
)


def sign(body, secret='whsec_for_testing', now=1_000_000):
    sig = hmac.new(secret.encode(), str(now).encode() + b'.' + body, hashlib.sha256).hexdigest()
    return f't={now},v1={sig}'


def event(event_id='evt_1', kind='customer.subscription.updated', status='active', created=1_000_000):
    return {'id':event_id, 'type':kind, 'created':created,
            'data': {'object': {'id':'sub_123','customer':'cus_123','status':status,
                                'items':{'data':[{'current_period_end':created+100}]}}}}


def test_valid_signature_and_payload():
    body=json.dumps(event()).encode()
    assert verify_stripe_signature(body,sign(body), 'whsec_for_testing', now=1_000_000)['id']=='evt_1'


def test_signed_tamper_fails():
    body=json.dumps(event()).encode()
    with pytest.raises(BillingError,match='signature_mismatch'):
        verify_stripe_signature(body+b'!',sign(body),'whsec_for_testing',now=1_000_000)


def test_expired_and_future_signatures_fail():
    body=json.dumps(event()).encode()
    for now in (1_000_301,999_699):
        with pytest.raises(BillingError,match='stale_webhook'):
            verify_stripe_signature(body,sign(body),'whsec_for_testing',now=now)


def test_missing_secret_fails_closed():
    body=json.dumps(event()).encode()
    with pytest.raises(BillingError,match='webhook_not_configured'):
        verify_stripe_signature(body,sign(body),'',now=1_000_000)


def test_event_idempotent_and_ordered(tmp_path):
    store=BillingStore(str(tmp_path/'events.sqlite3'))
    newer=event('evt_new','customer.subscription.updated','active',120)
    older=event('evt_old','customer.subscription.updated','past_due',100)
    assert store.accept(newer)=='recorded'
    assert store.accept(newer)=='duplicate'
    assert store.accept(older)=='recorded'
    with store.connect() as db:
        assert db.execute('select status,period_end from stripe_subscriptions').fetchone()==('active',220)
        assert db.execute('select count(*) from stripe_events').fetchone()[0]==2


def test_invoice_paid_not_entitlement(tmp_path):
    store=BillingStore(str(tmp_path/'events.sqlite3'))
    assert store.accept({'id':'evt_paid','type':'invoice.paid','created':100,
                         'data':{'object':{'id':'in_1','subscription':'sub_123'}}})=='recorded'
    with store.connect() as db:
        assert db.execute('select count(*) from stripe_subscriptions').fetchone()[0]==0


def test_deleted_cancels(tmp_path):
    store=BillingStore(str(tmp_path/'events.sqlite3'))
    assert store.accept(event('evt_2','customer.subscription.deleted','active',120))=='recorded'
    with store.connect() as db:
        assert db.execute('select status from stripe_subscriptions').fetchone()[0]=='canceled'


def test_invalid_subscription_identity_fails(tmp_path):
    store=BillingStore(str(tmp_path/'events.sqlite3'))
    e=event()
    e['data']['object']['customer']='not an id!!'
    with pytest.raises(BillingError,match='invalid_subscription_identity'):
        store.accept(e)


def test_no_client_side_or_unscoped_keys():
    with pytest.raises(BillingError,match='server_side_stripe_key_required'):
        list_merchant_subscriptions('pk_test_bad')


def test_incomplete_event_fails(tmp_path):
    store=BillingStore(str(tmp_path/'events.sqlite3'))
    with pytest.raises(BillingError,match='missing_event_object'):
        store.accept({'id':'evt_empty','type':'invoice.paid','created':10,'data':{}})