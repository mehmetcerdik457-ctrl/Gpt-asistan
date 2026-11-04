import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
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
        self.now[0] += eo.CODE_TTL
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

    def test_send_failure_invalidates_challenge_and_is_rate_limited(self):
        def fail(*_):
            raise OSError("smtp down")
        otp = eo.EmailOtp(self.tmp.name + "/o2.sqlite3", fail, lambda: 1)
        for _ in range(eo.MAX_REQUESTS):
            with self.assertRaises(eo.OtpDenied) as ctx:
                otp.request({"email": eo.DEFAULT_OWNER_EMAIL})
            self.assertEqual(ctx.exception.status, 502)
        with otp._db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM email_otp_v1 WHERE used=0").fetchone()[0], 0)
        with self.assertRaises(eo.OtpDenied) as ctx:
            otp.request({"email": eo.DEFAULT_OWNER_EMAIL})
        self.assertEqual(ctx.exception.status, 429)

    def test_unconfigured_smtp_fails_closed(self):
        otp = eo.EmailOtp(self.tmp.name + "/o3.sqlite3")
        with patch.dict("os.environ", {"SMTP_HOST": "", "SMTP_USER": "", "SMTP_PASSWORD": ""}):
            with self.assertRaises(eo.OtpDenied) as ctx:
                otp.request({"email": eo.DEFAULT_OWNER_EMAIL})
        self.assertEqual(ctx.exception.status, 503)

    def test_real_smtp_requires_stable_secret(self):
        config = {"SMTP_HOST": "smtp.example.com", "SMTP_USER": "owner@example.com",
                  "SMTP_PASSWORD": "test-password"}
        for secret in ("", "too-short", " " * 40):
            with self.subTest(secret_length=len(secret)), patch.dict("os.environ", {**config, "KRAL_OTP_SECRET": secret}):
                otp = eo.EmailOtp(self.tmp.name + "/secret.sqlite3")
                with patch.object(eo.smtplib, "SMTP") as smtp, self.assertRaises(eo.OtpDenied) as ctx:
                    otp.request({"email": eo.DEFAULT_OWNER_EMAIL})
                self.assertEqual(ctx.exception.status, 503)
                smtp.assert_not_called()

    def test_stable_secret_verifies_after_process_restart(self):
        with patch.dict("os.environ", {"KRAL_OTP_SECRET": "test-otp-secret-must-be-32-bytes-long"}):
            first = eo.EmailOtp(self.tmp.name + "/restart.sqlite3", self.mail, lambda: self.now[0])
            cid = first.request({"email": eo.DEFAULT_OWNER_EMAIL})["challenge_id"]
            second = eo.EmailOtp(self.tmp.name + "/restart.sqlite3", self.mail, lambda: self.now[0])
            self.assertTrue(second.verify({"challenge_id": cid, "code": self.mail.sent[-1][1]})["verified"])

    def test_concurrent_verification_consumes_code_once(self):
        cid, code = self.start()
        def verify(_):
            try:
                return self.otp.verify({"challenge_id": cid, "code": code})["verified"]
            except eo.OtpDenied:
                return False
        with ThreadPoolExecutor(max_workers=5) as workers:
            self.assertEqual(list(workers.map(verify, range(5))).count(True), 1)

    def test_malformed_inputs(self):
        for bad in ({"email": 5}, {"email": "x"}, {}):
            with self.assertRaises(eo.OtpDenied):
                self.otp.request(bad)
        for bad in ({"challenge_id": "short", "code": "123456"},
                    {"challenge_id": "a" * 20, "code": "12345"}, {}):
            with self.assertRaises(eo.OtpDenied):
                self.otp.verify(bad)


class SmtpTransport(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict("os.environ", {
            "SMTP_HOST": "smtp.example.com", "SMTP_PORT": "587", "SMTP_SSL": "",
            "SMTP_USER": "owner@example.com", "SMTP_PASSWORD": "test-password", "SMTP_FROM": "",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_starttls_precedes_credentials_and_empty_from_falls_back(self):
        with patch.object(eo.smtplib, "SMTP") as smtp, patch.object(eo.smtplib, "SMTP_SSL") as smtp_ssl:
            eo.send_via_smtp(eo.DEFAULT_OWNER_EMAIL, "123456")
        smtp.assert_called_once_with("smtp.example.com", 587, timeout=15)
        smtp_ssl.assert_not_called()
        self.assertEqual([call[0] for call in smtp.return_value.method_calls],
                         ["starttls", "login", "send_message"])
        message = smtp.return_value.send_message.call_args.args[0]
        self.assertEqual(message["From"], "owner@example.com")
        self.assertEqual(message["To"], eo.DEFAULT_OWNER_EMAIL)

    def test_implicit_tls_never_starts_plain_smtp(self):
        with patch.dict("os.environ", {"SMTP_SSL": "true", "SMTP_PORT": "465"}):
            with patch.object(eo.smtplib, "SMTP") as smtp, patch.object(eo.smtplib, "SMTP_SSL") as smtp_ssl:
                eo.send_via_smtp(eo.DEFAULT_OWNER_EMAIL, "123456")
        smtp.assert_not_called()
        self.assertEqual(smtp_ssl.call_args.args, ("smtp.example.com", 465))
        smtp_ssl.return_value.starttls.assert_not_called()
        smtp_ssl.return_value.login.assert_called_once_with("owner@example.com", "test-password")

    def test_tls_failure_never_sends_credentials(self):
        with patch.object(eo.smtplib, "SMTP") as smtp:
            smtp.return_value.starttls.side_effect = eo.smtplib.SMTPNotSupportedError("TLS unavailable")
            with self.assertRaises(eo.smtplib.SMTPNotSupportedError):
                eo.send_via_smtp(eo.DEFAULT_OWNER_EMAIL, "123456")
        smtp.return_value.login.assert_not_called()
        smtp.return_value.send_message.assert_not_called()


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
