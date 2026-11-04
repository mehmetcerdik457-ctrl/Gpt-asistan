import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from server import email_otp as eo
from server import gateway as g


class Mailbox:
    def __init__(self):
        self.sent = []

    def __call__(self, to, code):
        self.sent.append((to, code))


class EmailOtpUnit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = [1000]
        self.mail = Mailbox()
        self.otp = eo.EmailOtp(self.tmp.name + "/otp.sqlite3", self.mail, lambda: self.now[0])

    def tearDown(self):
        self.tmp.cleanup()

    def start(self):
        cid = self.otp.request({"email": eo.DEFAULT_OWNER_EMAIL})["challenge_id"]
        return cid, self.mail.sent[-1][1]

    def test_success_and_single_use(self):
        cid, code = self.start()
        self.assertEqual(self.mail.sent[-1][0], eo.DEFAULT_OWNER_EMAIL)
        self.assertRegex(code, r"^[0-9]{6}$")
        self.assertEqual(self.otp.verify({"challenge_id": cid, "code": code}), {"verified": True})
        with self.assertRaises(eo.OtpDenied):
            self.otp.verify({"challenge_id": cid, "code": code})

    def test_wrong_code_attempt_limit(self):
        cid, code = self.start()
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(eo.MAX_ATTEMPTS):
            with self.assertRaises(eo.OtpDenied):
                self.otp.verify({"challenge_id": cid, "code": wrong})
        with self.assertRaises(eo.OtpDenied):
            self.otp.verify({"challenge_id": cid, "code": code})

    def test_expiry(self):
        cid, code = self.start()
        self.now[0] += eo.CODE_TTL + 1
        with self.assertRaises(eo.OtpDenied):
            self.otp.verify({"challenge_id": cid, "code": code})

    def test_foreign_email_never_receives_code(self):
        with self.assertRaises(eo.OtpDenied) as ctx:
            self.otp.request({"email": "attacker@example.com"})
        self.assertEqual(ctx.exception.status, 403)
        self.assertEqual(self.mail.sent, [])

    def test_rate_limit(self):
        for _ in range(eo.MAX_REQUESTS):
            self.start()
        with self.assertRaises(eo.OtpDenied) as ctx:
            self.start()
        self.assertEqual(ctx.exception.status, 429)

    def test_send_failure_leaves_no_challenge(self):
        def fail(*_):
            raise OSError("smtp down")
        otp = eo.EmailOtp(self.tmp.name + "/o2.sqlite3", fail, lambda: 1)
        with self.assertRaises(eo.OtpDenied) as ctx:
            otp.request({"email": eo.DEFAULT_OWNER_EMAIL})
        self.assertEqual(ctx.exception.status, 502)

    def test_unconfigured_smtp_fails_closed(self):
        otp = eo.EmailOtp(self.tmp.name + "/o3.sqlite3")
        with patch.dict("os.environ", {"SMTP_HOST": "", "SMTP_USER": "", "SMTP_PASSWORD": ""}):
            with self.assertRaises(eo.OtpDenied) as ctx:
                otp.request({"email": eo.DEFAULT_OWNER_EMAIL})
        self.assertEqual(ctx.exception.status, 503)

    def test_malformed_inputs(self):
        for bad in ({"email": 5}, {"email": "x"}, {}):
            with self.assertRaises(eo.OtpDenied):
                self.otp.request(bad)
        for bad in ({"challenge_id": "short", "code": "123456"},
                    {"challenge_id": "a" * 20, "code": "12345"}, {}):
            with self.assertRaises(eo.OtpDenied):
                self.otp.verify(bad)


class EmailOtpHttp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mail = Mailbox()
        otp = eo.EmailOtp(self.tmp.name + "/otp.sqlite3", self.mail)
        with patch.dict("os.environ", {"OMEGA_OWNER_ID": "x"}):
            gateway = g.Gateway(g.Store(self.tmp.name + "/data.sqlite3"), object(), otp)
        self.gateway = gateway
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), g.handler_for(gateway))
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=3)
        self.gateway.tasks.close()
        self.tmp.cleanup()

    def post(self, path, data):
        req = urllib.request.Request(self.url + path, data=json.dumps(data).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            response = urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def test_full_flow_over_http(self):
        status, data = self.post(eo.REQUEST_PATH, {"email": eo.DEFAULT_OWNER_EMAIL})
        self.assertEqual(status, 200)
        code = self.mail.sent[-1][1]
        self.assertNotIn(code, json.dumps(data))
        status, data = self.post(eo.VERIFY_PATH, {"challenge_id": data["challenge_id"], "code": code})
        self.assertEqual((status, data["verified"]), (200, True))

    def test_http_rejects_foreign_email_and_bad_code(self):
        self.assertEqual(self.post(eo.REQUEST_PATH, {"email": "a@example.com"})[0], 403)
        _, data = self.post(eo.REQUEST_PATH, {"email": eo.DEFAULT_OWNER_EMAIL})
        wrong = "000000" if self.mail.sent[-1][1] != "000000" else "111111"
        self.assertEqual(self.post(eo.VERIFY_PATH, {"challenge_id": data["challenge_id"], "code": wrong})[0], 403)


if __name__ == "__main__":
    unittest.main()
