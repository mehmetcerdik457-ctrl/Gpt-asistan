"""Bounded Google-auth network transport; all HTTP responses are synthetic."""
from datetime import datetime, timezone
import json
import time
import unittest
from unittest.mock import Mock, patch, sentinel

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from google.auth import crypt, jwt
from google.auth.exceptions import GoogleAuthError, TransportError

from server.play_google_oauth import PlayPublisherOAuth, _default_request
from server.play_rtdn import verify_google_oidc
from server.tests import test_play_google_oauth as oauth_fixture


class GoogleTransportTests(unittest.TestCase):
    def test_default_timeout_and_request_data_forwarded_unchanged(self):
        underlying = Mock(return_value=sentinel.response)
        headers = {"Authorization": "Bearer synthetic-only"}
        body = b"synthetic-body"
        with patch("google.auth.transport.requests.Request", return_value=underlying):
            transport = _default_request()
        self.assertIs(transport("https://oauth2.googleapis.com/token", method="POST",
                                body=body, headers=headers), sentinel.response)
        underlying.assert_called_once_with(url="https://oauth2.googleapis.com/token",
            method="POST", body=body, headers=headers, timeout=8)
        self.assertIs(underlying.call_args.kwargs["headers"], headers)
        self.assertIs(underlying.call_args.kwargs["body"], body)

    def test_explicit_shorter_timeouts_preserved_and_larger_timeouts_capped(self):
        underlying = Mock(return_value=sentinel.response)
        with patch("google.auth.transport.requests.Request", return_value=underlying):
            transport = _default_request()
        for supplied, expected in ((0.25, 0.25), (2, 2), (8, 8), (120, 8), (10**1000, 8)):
            with self.subTest(timeout=supplied):
                transport("https://example.test/certs", timeout=supplied)
                self.assertEqual(underlying.call_args.kwargs["timeout"], expected)

    def test_invalid_or_unbounded_timeouts_rejected_before_network(self):
        underlying = Mock()
        with patch("google.auth.transport.requests.Request", return_value=underlying):
            transport = _default_request()
        for invalid in (None, 0, -1, True, False, float("nan"), float("inf"), "PRIVATE_TIMEOUT", (1, 2)):
            with self.subTest(kind=type(invalid).__name__):
                with self.assertRaisesRegex(ValueError, "^GOOGLE_TRANSPORT_TIMEOUT_INVALID$"):
                    transport("https://example.test/certs", timeout=invalid)
        underlying.assert_not_called()

    def test_transport_failure_does_not_expose_url_header_body_or_raw_error(self):
        underlying = Mock(side_effect=RuntimeError("PRIVATE_TRANSPORT_DETAILS"))
        with patch("google.auth.transport.requests.Request", return_value=underlying):
            transport = _default_request()
        with self.assertRaises(TransportError) as error:
            transport("https://example.test/PRIVATE_URL", body=b"PRIVATE_BODY",
                      headers={"Authorization": "PRIVATE_HEADER"})
        self.assertEqual(str(error.exception), "GOOGLE_TRANSPORT_UNAVAILABLE")
        self.assertIsNone(error.exception.__cause__)

    def test_default_oauth_refresh_uses_bounded_request_factory(self):
        credentials = oauth_fixture.FakeCredentials(ttl=-1)
        underlying = Mock(return_value=sentinel.response)
        def refresh(request):
            self.assertIs(request("https://oauth2.googleapis.com/token", method="POST",
                                  body=b"synthetic-grant", timeout=120), sentinel.response)
            credentials.token = "refreshed-synthetic-access-token"
            credentials.expiry = datetime.fromtimestamp(oauth_fixture.NOW + 3600, timezone.utc)
        credentials.refresh = refresh
        supplier = PlayPublisherOAuth(service_account_email=oauth_fixture.EMAIL,
            credential_loader=lambda **_: (credentials, "synthetic-project"),
            enabled=lambda: True, now=lambda: oauth_fixture.NOW)
        with patch("google.auth.transport.requests.Request", return_value=underlying):
            self.assertEqual(supplier(), "refreshed-synthetic-access-token")
        self.assertEqual(underlying.call_args.kwargs["timeout"], 8)

    def test_oidc_cert_fetch_uses_same_bounded_transport_and_google_verifier(self):
        underlying = Mock(return_value=sentinel.response)
        expected = {"aud": "https://push.example.test", "email_verified": True}
        def google_verifier(token, request, *, audience):
            self.assertEqual(token, "synthetic-id-token")
            self.assertEqual(audience, "https://push.example.test")
            self.assertIs(request("https://www.googleapis.com/oauth2/v1/certs",
                                  method="GET", timeout=120), sentinel.response)
            return expected
        with patch("google.auth.transport.requests.Request", return_value=underlying), \
                patch("google.oauth2.id_token.verify_oauth2_token", side_effect=google_verifier) as verify:
            self.assertIs(verify_google_oidc("synthetic-id-token", "https://push.example.test"), expected)
        verify.assert_called_once()
        self.assertEqual(underlying.call_args.kwargs["timeout"], 8)

    def test_real_google_library_still_enforces_signature_expiry_audience_and_issuer(self):
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = private.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        public = private.public_key().public_bytes(serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        signer = crypt.RSASigner.from_string(pem, key_id="synthetic-key")
        now = int(time.time())
        claims = {"iss": "https://accounts.google.com", "aud": "https://push.example.test",
                  "iat": now - 10, "exp": now + 300,
                  "email": oauth_fixture.EMAIL, "email_verified": True}
        response = Mock(status=200, data=json.dumps({"synthetic-key": public}).encode())
        underlying = Mock(return_value=response)
        with patch("google.auth.transport.requests.Request", return_value=underlying):
            encoded = jwt.encode(signer, claims).decode()
            verified = verify_google_oidc(encoded, claims["aud"])
            self.assertEqual(verified, claims)
            cases = (
                (jwt.encode(signer, dict(claims, iat=now-3600, exp=now-60)).decode(), claims["aud"]),
                (encoded, "https://wrong.example.test"),
                (jwt.encode(signer, dict(claims, iss="https://wrong.example.test")).decode(), claims["aud"]),
                # Change the signed payload while retaining the old signature.
                (encoded.split(".")[0] + ".eyJhdWQiOiJ0YW1wZXJlZCJ9." + encoded.split(".")[2], claims["aud"]),
            )
            for token, audience in cases:
                with self.subTest(audience=audience), self.assertRaises((ValueError, GoogleAuthError)):
                    verify_google_oidc(token, audience)
        self.assertTrue(underlying.call_args_list)
        self.assertTrue(all(call.kwargs["timeout"] == 8 for call in underlying.call_args_list))


if __name__ == "__main__":
    unittest.main()
