"""Independent strict-type/encoding regressions for canonical RTDN/access.

All identity/provider inputs here are synthetic. No credential discovery,
network request, provider operation or database migration occurs.
"""
import base64
from dataclasses import replace
import itertools
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import unittest
from unittest.mock import patch

from server.play_entitlement_gate import (
    PACKAGE, VerifiedPlayPurchase, entitlement_allowed, token_digest,
)
from server.play_rtdn import PlayRtdnProcessor, RtdnDenied
from server.play_account_id import obfuscated_play_account_id
from server.play_google_api import get_subscription_v2, PlayVerificationError
from server.play_subscription_mapper import verify_and_map_subscription, PlayMappingError


NOW = 1_794_000_000
AUDIENCE = 'https://play.example.test/api/v1/play/rtdn'
EMAIL = 'push@orba-test.iam.gserviceaccount.com'
SUBSCRIPTION = 'projects/orba-test/subscriptions/orba-test-rtdn'
PRODUCT = 'orba_pro_monthly'
JWT = 'synthetic.header.signature'


def event(*, test=False):
    result = {'version': '1.0', 'packageName': PACKAGE,
              'eventTimeMillis': str(NOW * 1000)}
    if test:
        result['testNotification'] = {'version': '1.0'}
    else:
        result['subscriptionNotification'] = {
            'version': '1.0', 'notificationType': 4, 'purchaseToken': 'token-one',
        }
    return result


def wrap(payload=None, *, encoded=None, message=None):
    if encoded is None:
        payload = json.dumps(event() if payload is None else payload).encode()
        encoded = base64.b64encode(payload).decode()
    msg = {'messageId': 'strict-boundary-message', 'data': encoded}
    if message is not None:
        msg.update(message)
    return json.dumps({'subscription': SUBSCRIPTION, 'message': msg}).encode()


class StrictRtdnBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.claims = {'iss': 'https://accounts.google.com', 'aud': AUDIENCE,
                       'email': EMAIL, 'email_verified': True,
                       'iat': NOW - 10, 'exp': NOW + 100}
        self.processor = PlayRtdnProcessor(
            audience=AUDIENCE, service_account_email=EMAIL,
            subscription=SUBSCRIPTION, allowed_products={PRODUCT},
            server_secret=b'synthetic-test-server-secret-32-bytes',
            oauth_supplier=lambda: self.fail('unexpected OAuth call'),
            db_factory=lambda: self.fail('unexpected DB call'),
            verifier=lambda *_: self.claims, clock=lambda: NOW,
        )

    def denied(self, body):
        with self.assertRaisesRegex(RtdnDenied, '^RTDN_PAYLOAD_INVALID$'):
            self.processor.unpack(body)

    def test_only_boolean_true_email_verification_is_accepted(self):
        self.processor.authenticate('Bearer ' + JWT)
        for value in ('true', 'false', 1, 0, False, None, [], {}):
            with self.subTest(type=type(value).__name__):
                self.claims['email_verified'] = value
                with self.assertRaisesRegex(RtdnDenied, '^RTDN_AUTH_DENIED$'):
                    self.processor.authenticate('Bearer ' + JWT)

    def test_malformed_issuer_types_are_denied_without_python_type_errors(self):
        for value in ([], {}, True, None, 1):
            with self.subTest(type=type(value).__name__):
                self.claims['iss'] = value
                with self.assertRaisesRegex(RtdnDenied, '^RTDN_AUTH_DENIED$'):
                    self.processor.authenticate('Bearer ' + JWT)

    def test_invalid_clock_fails_closed_with_fixed_auth_error(self):
        for value in (True, None, float('nan'), float('inf'), 'private-clock-value'):
            with self.subTest(type=type(value).__name__):
                self.processor.clock = lambda: value
                with self.assertRaisesRegex(RtdnDenied, '^RTDN_AUTH_DENIED$'):
                    self.processor.authenticate('Bearer ' + JWT)

    def test_unverified_identity_cannot_parse_payload_or_reach_dependencies(self):
        self.claims['email_verified'] = 'true'
        with patch.object(self.processor, 'unpack', side_effect=AssertionError('parsed before auth')) as unpack:
            with self.assertRaisesRegex(RtdnDenied, '^RTDN_AUTH_DENIED$'):
                self.processor.process(authorization='Bearer ' + JWT, raw=wrap())
        unpack.assert_not_called()

    def test_duplicate_outer_and_nested_json_members_are_denied(self):
        good = wrap()
        self.denied(b'{"subscription":"private-duplicate-subscription",' + good[1:])
        encoded = base64.b64encode(json.dumps(event()).encode()).decode()
        self.denied(json.dumps({'subscription': SUBSCRIPTION}).encode()[:-1]
            + b',"message":{"messageId":"first","messageId":"last","data":'
            + json.dumps(encoded).encode() + b'}}')

    def test_duplicate_notification_members_are_denied(self):
        raw = json.dumps(event()).replace(
            '"notificationType": 4', '"notificationType": 13, "notificationType": 4')
        self.denied(wrap(encoded=base64.b64encode(raw.encode()).decode()))

    def test_noncanonical_base64_pad_bits_are_denied(self):
        raw = json.dumps(event()).encode()
        while len(raw) % 3 == 0:
            raw += b' '
        encoded = base64.b64encode(raw).decode()
        alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
        index = len(encoded.rstrip('=')) - 1
        altered = encoded[:index] + alphabet[alphabet.index(encoded[index]) ^ 1] + encoded[index + 1:]
        self.assertNotEqual(encoded, altered)
        self.assertEqual(base64.b64decode(altered, validate=True), raw)
        self.denied(wrap(encoded=altered))

    def test_notification_payload_families_are_mutually_exclusive(self):
        keys = ('subscriptionNotification', 'testNotification',
                'oneTimeProductNotification', 'voidedPurchaseNotification',
                'pendingRefundReviewNotification', 'futureNotification')
        for primary in ('testNotification', 'subscriptionNotification'):
            original = event(test=primary == 'testNotification')
            for other in keys:
                if other == primary:
                    continue
                with self.subTest(primary=primary, other=other):
                    self.denied(wrap(original | {other: {'version': '1.0'}}))

    def test_nonfinite_json_is_rejected_even_in_unselected_fields(self):
        for number in ('NaN', 'Infinity', '-Infinity', '1e999'):
            with self.subTest(number=number):
                body = wrap()
                self.denied(body[:-1] + b',"ignored":' + number.encode() + b'}')
                raw = json.dumps(event())[:-1] + ',"ignored":' + number + '}'
                self.denied(wrap(encoded=base64.b64encode(raw.encode()).decode()))

    def test_deeply_nested_json_is_a_sanitized_denial(self):
        deep = b'[' * 2000 + b'0' + b']' * 2000
        self.denied(deep)
        self.denied(wrap(encoded=base64.b64encode(deep).decode()))

    def test_conflicting_message_identifier_aliases_are_rejected(self):
        self.denied(wrap(message={'message_id': 'different-message'}))

    def test_existing_canonical_and_legacy_single_identifier_formats_still_work(self):
        self.assertEqual(self.processor.unpack(wrap())[0], 'strict-boundary-message')
        legacy = json.loads(wrap())
        legacy['message']['message_id'] = legacy['message'].pop('messageId')
        self.assertEqual(self.processor.unpack(json.dumps(legacy).encode())[0], 'strict-boundary-message')
        self.assertTrue(self.processor.unpack(wrap(event(test=True)))[3])

    def test_unknown_subscription_type_and_deep_ignored_values_are_denied(self):
        payload = event()
        payload['subscriptionNotification']['notificationType'] = 99
        self.denied(wrap(payload))
        body = wrap()
        self.denied(body[:-1] + b',"ignored":' + b'[' * 100 + b'0' + b']' * 100 + b'}')


class StrictEntitlementBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.token_hash = token_digest('token-one')
        self.purchase = VerifiedPlayPurchase(
            PACKAGE, PRODUCT, self.token_hash, 'alice', NOW * 1000 + 10000,
            'SUBSCRIPTION_STATE_ACTIVE', True, True,
        )

    def allowed(self, purchase):
        return entitlement_allowed(purchase, owner_id='alice', product_id=PRODUCT,
                                   token_sha256=self.token_hash, now_ms=NOW * 1000)

    def test_provenance_and_acknowledgement_require_literal_boolean_true(self):
        self.assertTrue(self.allowed(self.purchase))
        for field, value in itertools.product(('acknowledged', 'verified_by_google_api'),
                                             ('true', 'false', 1, 2, [], {}, None, False)):
            with self.subTest(field=field, type=type(value).__name__):
                self.assertFalse(self.allowed(replace(self.purchase, **{field: value})))

    def test_malformed_purchase_digest_is_denied_without_comparison_errors(self):
        for value in (None, True, 1, [], {}, b'x' * 64, 'é' * 64, 'bad'):
            with self.subTest(type=type(value).__name__):
                self.assertFalse(self.allowed(replace(self.purchase, purchase_token_sha256=value)))

    def test_boolean_expiry_and_unknown_states_do_not_grant(self):
        for changes in ({'expires_at_ms': True}, {'subscription_state': []},
                        {'subscription_state': {}}, {'subscription_state': 'unknown'}):
            with self.subTest(field=next(iter(changes))):
                self.assertFalse(self.allowed(replace(self.purchase, **changes)))

    def test_known_paid_through_and_grace_states_preserve_legitimate_access(self):
        for state in ('SUBSCRIPTION_STATE_ACTIVE', 'SUBSCRIPTION_STATE_IN_GRACE_PERIOD',
                      'SUBSCRIPTION_STATE_CANCELED'):
            with self.subTest(state=state):
                self.assertTrue(self.allowed(replace(self.purchase, subscription_state=state)))
                self.assertFalse(self.allowed(replace(self.purchase,
                    subscription_state=state, expires_at_ms=NOW * 1000)))


class ProviderResponse:
    status = 200

    def __init__(self, raw):
        self.raw = raw

    def read(self, size):
        return self.raw[:size]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class StrictPlayProviderBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.secret = b'synthetic-test-server-secret-32-bytes'
        self.reference = obfuscated_play_account_id(
            authenticated_owner_id='alice', server_secret=self.secret)
        self.provider = {
            'subscriptionState': 'SUBSCRIPTION_STATE_ACTIVE',
            'acknowledgementState': 'ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED',
            'externalAccountIdentifiers': {'obfuscatedExternalAccountId': self.reference},
            'lineItems': [{'productId': PRODUCT, 'expiryTime': '2030-01-01T00:00:00Z'}],
        }

    def lookup(self, raw):
        return get_subscription_v2('token-one', 'synthetic-oauth',
            opener=lambda *_args, **_kwargs: ProviderResponse(raw))

    def test_duplicate_provider_account_claims_are_not_trusted(self):
        raw = json.dumps(self.provider).replace(
            '"obfuscatedExternalAccountId":',
            '"obfuscatedExternalAccountId":"forged", "obfuscatedExternalAccountId":')
        with self.assertRaisesRegex(PlayVerificationError, '^GOOGLE_PLAY_INVALID_RESPONSE$'):
            self.lookup(raw.encode())

    def test_nonfinite_provider_values_fail_closed_even_when_not_selected(self):
        for number in ('NaN', 'Infinity', '-Infinity', '1e999'):
            with self.subTest(number=number):
                raw = json.dumps(self.provider)[:-1] + ',"ignored":' + number + '}'
                with self.assertRaisesRegex(PlayVerificationError, '^GOOGLE_PLAY_INVALID_RESPONSE$'):
                    self.lookup(raw.encode())

    def test_deep_provider_values_are_a_fixed_error_not_a_recursion_error(self):
        raw = json.dumps(self.provider).encode()[:-1] + b',"ignored":'
        raw += b'[' * 2000 + b'0' + b']' * 2000 + b'}'
        with self.assertRaisesRegex(PlayVerificationError, '^GOOGLE_PLAY_INVALID_RESPONSE$'):
            self.lookup(raw)

    def test_non_ascii_account_claim_is_denied_without_hmac_type_error(self):
        self.provider['externalAccountIdentifiers']['obfuscatedExternalAccountId'] = 'é' * 64
        with self.assertRaisesRegex(PlayMappingError, '^PLAY_ACCOUNT_BINDING_MISMATCH$'):
            verify_and_map_subscription(purchase_token='token-one', access_token='synthetic-oauth',
                owner_id='alice', product_id=PRODUCT, server_secret=self.secret,
                opener=lambda *_args, **_kwargs: ProviderResponse(json.dumps(self.provider).encode()))

    def test_invalid_server_credentials_never_reach_transport(self):
        for token in ('private token', 'private\tvalue', 'private\x00value', 'é', 'x' * 8193):
            with self.subTest(size=len(token)):
                with self.assertRaisesRegex(PlayVerificationError, '^INVALID_SERVER_CREDENTIAL$'):
                    get_subscription_v2('token-one', token,
                        opener=lambda *_args, **_kwargs: self.fail('credential reached transport'))

    def test_authenticated_default_transport_never_follows_http_redirects(self):
        # The production URL remains Google-only. Patch its fixed constant only
        # inside this synthetic localhost test to exercise urllib's real handler.
        requests = []
        provider_raw = json.dumps(self.provider).encode()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(handler):
                requests.append(handler.path)
                if handler.path == '/capture':
                    handler.send_response(200)
                    handler.send_header('Content-Length', str(len(provider_raw)))
                    handler.end_headers()
                    handler.wfile.write(provider_raw)
                    return
                handler.send_response(302)
                handler.send_header('Location', '/capture')
                handler.send_header('Content-Length', '0')
                handler.end_headers()

            def log_message(self, *_args):
                pass

        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch('server.play_google_api.API',
                       'http://127.0.0.1:' + str(server.server_port) + '/applications'):
                with self.assertRaises(PlayVerificationError):
                    get_subscription_v2('token-one', 'synthetic-oauth')
            self.assertEqual(len(requests), 1)
            self.assertNotIn('/capture', requests)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
