import io
import json
import unittest
from unittest.mock import Mock
from server.play_google_api import get_subscription_v2, PlayVerificationError

class Response:
    status = 200
    def __init__(self, payload): self.payload = payload
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, size): return self.payload

class Tests(unittest.TestCase):
    def test_successful_readonly_lookup(self):
        data = {"subscriptionState":"SUBSCRIPTION_STATE_ACTIVE","lineItems":[{"productId":"orba_pro_monthly"}]}
        def opener(req, timeout):
            self.assertEqual(req.get_method(), "GET")
            self.assertIn("/purchases/subscriptionsv2/tokens/", req.full_url)
            self.assertEqual(req.get_header("Authorization"), "Bearer server-token")
            self.assertEqual(timeout, 8)
            return Response(json.dumps(data).encode())
        self.assertEqual(get_subscription_v2("play-token", "server-token", opener=opener), data)

    def test_bad_purchase_token(self):
        with self.assertRaises(PlayVerificationError): get_subscription_v2("bad/token", "access")
    def test_missing_oauth(self):
        with self.assertRaises(PlayVerificationError): get_subscription_v2("valid", "")
    def test_header_injection(self):
        with self.assertRaises(PlayVerificationError): get_subscription_v2("valid", "abc\r\nInjected: x")
    def test_invalid_json(self):
        with self.assertRaises(PlayVerificationError): get_subscription_v2("valid", "access", opener=lambda *_args, **_kwargs: Response(b"not-json"))
    def test_missing_line_items(self):
        with self.assertRaises(PlayVerificationError): get_subscription_v2("valid", "access", opener=lambda *_args, **_kwargs: Response(b'{"subscriptionState":"ACTIVE"}'))
    def test_oversize(self):
        with self.assertRaises(PlayVerificationError): get_subscription_v2("valid", "access", opener=lambda *_args, **_kwargs: Response(b"x"*262145))
    def test_transport_failure(self):
        def fail(*_args, **_kwargs): raise TimeoutError()
        with self.assertRaises(PlayVerificationError): get_subscription_v2("valid", "access", opener=fail)
    def test_non_200(self):
        class BadResponse(Response): status=403
        with self.assertRaises(PlayVerificationError): get_subscription_v2("valid", "access", opener=lambda *_args, **_kwargs: BadResponse(b"{}"))

if __name__ == "__main__": unittest.main()
