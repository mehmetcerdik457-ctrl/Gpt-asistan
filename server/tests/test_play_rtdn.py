"""No live Google calls; authenticated RTDN audit and real localhost HTTP tests."""
import base64
import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from server.play_entitlement_gate import PACKAGE
from server.play_owner_binding import initialize, bind_or_verify_owner
from server.play_rtdn import (
    PlayRtdnProcessor, RtdnDenied, RtdnRetry, initialize_rtdn, ENDPOINT,
)
from server.tests.test_play_acknowledgement_service import FakeGoogle, purchase, SECRET
from server.tests import test_gateway as gateway_fixture

NOW = 1794000000
AUDIENCE = "https://play.example.test/api/v1/play/rtdn"
EMAIL = "push@orba-test.iam.gserviceaccount.com"
SUB = "projects/orba-test/subscriptions/orba-test-rtdn"
PRODUCT = "orba_pro_monthly"
JWT = "synthetic.header.signature"


def event(*, token="token-one", kind=4, package=PACKAGE, is_test=False):
    data = {
        "version": "1.0",
        "packageName": package,
        "eventTimeMillis": str(NOW * 1000),
    }
    if is_test:
        data["testNotification"] = {"version": "1.0"}
    else:
        data["subscriptionNotification"] = {
            "version": "1.0", "notificationType": kind, "purchaseToken": token}
    return data


def wrapped(*, msgid="message-001", data=None, subscription=SUB):
    raw = json.dumps(event() if data is None else data).encode("utf-8")
    return json.dumps({
        "subscription": subscription,
        "message": {"messageId": msgid, "data": base64.b64encode(raw).decode("ascii")},
    }).encode("utf-8")


def claims(**overrides):
    value = {
        "iss": "https://accounts.google.com",
        "aud": AUDIENCE,
        "email": EMAIL,
        "email_verified": True,
        "iat": NOW - 20,
        "exp": NOW + 200,
    }
    value.update(overrides)
    return value


def fake_provider(owner="alice", state="SUBSCRIPTION_STATE_ACTIVE"):
    return purchase(owner=owner, state=state,
                    ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED")


class RtdnUnitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dbpath = self.tmp.name + "/rtdn-private.sqlite3"
        with sqlite3.connect(self.dbpath) as db:
            initialize(db)
            initialize_rtdn(db)
        self.google = FakeGoogle(fake_provider())
        self.oauth_calls = 0
        self.verifier_calls = 0
        self.fake_claims = claims()

        def oauth():
            self.oauth_calls += 1
            return "synthetic-google-publisher-oauth"

        def verify(token, audience):
            self.verifier_calls += 1
            self.assertEqual(token, JWT)
            self.assertEqual(audience, AUDIENCE)
            return self.fake_claims

        self.processor = PlayRtdnProcessor(
            audience=AUDIENCE, service_account_email=EMAIL, subscription=SUB,
            allowed_products={PRODUCT}, server_secret=SECRET,
            db_factory=lambda: sqlite3.connect(self.dbpath),
            oauth_supplier=oauth, verifier=verify,
            provider_opener=lambda request, timeout: self.google(request, timeout),
            clock=lambda: NOW,
        )

    def rows(self):
        with sqlite3.connect(self.dbpath) as db:
            return db.execute(
                "SELECT outcome,purchase_token_digest FROM play_rtdn_audit"
            ).fetchall()

    def run_event(self, raw=None, bearer="Bearer " + JWT):
        return self.processor.process(
            authorization=bearer, raw=wrapped() if raw is None else raw)

    def bind(self, owner="alice"):
        with sqlite3.connect(self.dbpath) as db:
            bind_or_verify_owner(db, purchase_token="token-one",
                                 authenticated_owner_id=owner, now_ms=NOW * 1000)

    def test_known_owner_requires_fresh_google_state_and_audits_only(self):
        self.bind()
        self.assertTrue(self.run_event())
        self.assertEqual(self.rows()[0][0], "RECHECKED_BOUND")
        self.assertEqual(len(self.google.requests), 1)
        self.assertEqual(self.google.requests[0][0], "GET")
        self.assertEqual(self.rows()[0][1], hashlib.sha256(b"token-one").hexdigest())
        with sqlite3.connect(self.dbpath) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM play_token_owners").fetchone()[0], 1)

    def test_exact_duplicate_skips_second_provider_call(self):
        self.assertTrue(self.run_event())
        self.assertFalse(self.run_event())
        self.assertEqual(len(self.google.requests), 1)
        self.assertEqual(len(self.rows()), 1)

    def test_changed_message_under_same_id_denied(self):
        self.assertTrue(self.run_event())
        with self.assertRaisesRegex(RtdnDenied, "RTDN_MESSAGE_ID_CONFLICT"):
            self.run_event(wrapped(data=event(kind=13)))
        self.assertEqual(len(self.rows()), 1)

    def test_unbound_purchase_does_not_bind_owner(self):
        self.assertTrue(self.run_event())
        self.assertEqual(self.rows()[0][0], "RECHECKED_UNBOUND")
        with sqlite3.connect(self.dbpath) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM play_token_owners").fetchone()[0], 0)

    def test_test_notification_does_not_request_oauth_or_create_entitlement(self):
        self.assertTrue(self.run_event(wrapped(data=event(is_test=True))))
        self.assertEqual(self.rows(), [("TEST", None)])
        self.assertEqual(self.oauth_calls, 0)
        self.assertEqual(self.google.requests, [])

    def test_missing_bearer_does_not_reach_provider(self):
        with self.assertRaisesRegex(RtdnDenied, "RTDN_AUTH_DENIED"):
            self.run_event(bearer="")
        self.assertEqual(self.verifier_calls, 0)
        self.assertEqual(self.rows(), [])

    def test_google_oidc_signature_verifier_failure_denied(self):
        self.processor.verifier = lambda *_: (_ for _ in ()).throw(ValueError("invalid sig"))
        with self.assertRaisesRegex(RtdnDenied, "RTDN_AUTH_DENIED"):
            self.run_event()
        self.assertEqual(self.rows(), [])

    def test_wrong_identity_claims_denied(self):
        for k, v in (
            ("aud", "https://attacker.test/"),
            ("email", "attacker@else.iam.gserviceaccount.com"),
            ("iss", "https://attacker.test"),
            ("email_verified", False),
            ("iat", NOW + 1),
            ("exp", NOW - 1),
        ):
            with self.subTest(k=k):
                self.fake_claims = claims(**{k: v})
                with self.assertRaisesRegex(RtdnDenied, "RTDN_AUTH_DENIED"):
                    self.run_event()
                self.assertEqual(self.rows(), [])

    def test_wrong_pubsub_subscription_denied(self):
        with self.assertRaisesRegex(RtdnDenied, "RTDN_PAYLOAD_INVALID"):
            self.run_event(wrapped(subscription="projects/attacker/subscriptions/else"))
        self.assertEqual(self.oauth_calls, 0)

    def test_wrong_package_denied_before_google(self):
        with self.assertRaises(RtdnDenied):
            self.run_event(wrapped(data=event(package="different.package")))
        self.assertEqual(self.oauth_calls, 0)

    def test_invalid_purchase_token_denied_before_google(self):
        with self.assertRaises(RtdnDenied):
            self.run_event(wrapped(data=event(token="bad/token")))
        self.assertEqual(self.oauth_calls, 0)

    def test_boolean_notification_type_denied(self):
        with self.assertRaises(RtdnDenied):
            self.run_event(wrapped(data=event(kind=True)))
        self.assertEqual(self.oauth_calls, 0)

    def test_invalid_b64_denied(self):
        bad = json.loads(wrapped())
        bad["message"]["data"] = "??"
        with self.assertRaises(RtdnDenied):
            self.run_event(json.dumps(bad).encode())
        self.assertEqual(self.oauth_calls, 0)

    def test_malformed_json_and_oversize_denied(self):
        for body in (b"{", b"x" * 16385, b""):
            with self.subTest(length=len(body)), self.assertRaises(RtdnDenied):
                self.run_event(body)
        self.assertEqual(self.rows(), [])

    def test_provider_failure_is_retryable_no_success_ledger(self):
        self.google = FakeGoogle(urllib.error.URLError("offline"))
        with self.assertRaisesRegex(RtdnRetry, "RTDN_PROVIDER_RECHECK_UNAVAILABLE"):
            self.run_event()
        self.assertEqual(self.rows(), [])
        self.google = FakeGoogle(fake_provider())
        self.assertTrue(self.run_event())
        self.assertEqual(len(self.rows()), 1)

    def test_wrong_bound_owner_causes_retry_without_audit(self):
        self.bind(owner="alice")
        self.google = FakeGoogle(fake_provider(owner="bob"))
        with self.assertRaises(RtdnRetry):
            self.run_event()
        self.assertEqual(self.rows(), [])

    def test_unknown_product_causes_retry_without_audit(self):
        bad = fake_provider()
        bad["lineItems"][0]["productId"] = "wrong"
        self.google = FakeGoogle(bad)
        with self.assertRaises(RtdnRetry):
            self.run_event()
        self.assertEqual(self.rows(), [])

    def test_revocation_event_also_fetches_provider_not_directly_revoke(self):
        self.bind()
        self.google = FakeGoogle(fake_provider(state="SUBSCRIPTION_STATE_EXPIRED"))
        self.assertTrue(self.run_event(wrapped(data=event(kind=13))))
        self.assertEqual(self.rows()[0][0], "RECHECKED_BOUND")
        with sqlite3.connect(self.dbpath) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM play_token_owners").fetchone()[0], 1)

    def test_missing_migration_fails_retry_not_grant(self):
        self.processor.db_factory = lambda: sqlite3.connect(":memory:")
        with self.assertRaises(RtdnRetry):
            self.run_event()
        self.assertEqual(self.rows(), [])

    def test_invalid_provisioning_denied(self):
        config = dict(audience=AUDIENCE, service_account_email=EMAIL,
                      subscription=SUB, allowed_products={PRODUCT},
                      server_secret=SECRET,
                      db_factory=lambda: sqlite3.connect(":memory:"),
                      oauth_supplier=lambda: "token")
        for field, value in (
            ("audience", "http://not-https"),
            ("service_account_email", "fake@example.com"),
            ("subscription", "bad"),
            ("allowed_products", set()),
            ("server_secret", b"short"),
        ):
            with self.subTest(field=field):
                p = dict(config)
                p[field] = value
                with self.assertRaises(ValueError):
                    PlayRtdnProcessor(**p)


class RtdnHttpTests(unittest.TestCase):
    def setUp(self):
        self.owner_fixture = gateway_fixture.GatewayHttpTests(
            methodName="test_no_provider_calls_without_auth")
        self.owner_fixture.setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.dbpath = self.tmp.name + "/private-play.sqlite3"
        with sqlite3.connect(self.dbpath) as db:
            initialize(db)
            initialize_rtdn(db)
        self.google = FakeGoogle(fake_provider())
        self.processor = PlayRtdnProcessor(
            audience=AUDIENCE, service_account_email=EMAIL, subscription=SUB,
            allowed_products={PRODUCT}, server_secret=SECRET,
            db_factory=lambda: sqlite3.connect(self.dbpath),
            oauth_supplier=lambda: "synthetic-oauth",
            verifier=lambda token, audience: claims(),
            provider_opener=lambda req, timeout: self.google(req, timeout),
            clock=lambda: NOW)
        self.owner_fixture.gateway.rtdn_processor = self.processor
        self.env = patch.dict(os.environ, {"ORBA_PLAY_RTDN_ENABLED": "YES"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()
        self.owner_fixture.tearDown()

    def post(self, raw=None, header="Bearer " + JWT):
        headers = {"Content-Type": "application/json"}
        if header is not None:
            headers["Authorization"] = header
        request = urllib.request.Request(
            self.owner_fixture.url + ENDPOINT,
            data=wrapped(data=event(is_test=True)) if raw is None else raw,
            headers=headers, method="POST")
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.status, json.loads(response.read())

    def test_authenticated_test_push_audit_http_200_no_grant(self):
        status, data = self.post()
        self.assertEqual(status, 200)
        self.assertEqual(data["rtdn"], "AUDITED")
        self.assertIs(data["entitlement_changed"], False)
        self.assertEqual(self.owner_fixture.provider.calls, [])

    def test_missing_oidc_http_403(self):
        status, data = self.post(header=None)
        self.assertEqual((status, data["error"]), (403, "RTDN_HEADERS_INVALID"))

    def test_disabled_http_503_without_provider(self):
        with patch.dict(os.environ, {"ORBA_PLAY_RTDN_ENABLED": "NO"}):
            status, data = self.post()
        self.assertEqual((status, data["error"]), (503, "RTDN_NOT_CONFIGURED"))

    def test_duplicate_push_http_200_with_no_entitlement(self):
        self.assertEqual(self.post()[0], 200)
        status, data = self.post()
        self.assertEqual(status, 200)
        self.assertEqual(data["rtdn"], "DUPLICATE")
        self.assertIs(data["entitlement_changed"], False)

    def test_provider_unavailable_http_503_for_pubsub_retry(self):
        self.google = FakeGoogle(urllib.error.URLError("offline"))
        status, data = self.post(raw=wrapped())
        self.assertEqual((status, data["error"]), (503, "RTDN_RETRY_REQUIRED"))


if __name__ == "__main__":
    unittest.main()
