"""E-mail one-time code (OTP) login for the single owner.

The code is generated and e-mailed only by this server. The destination is the
configured owner address; a client-supplied address must match it and can never
redirect the code. Codes are stored only as HMAC digests, expire, are single use,
and are limited per challenge and per time window. SMTP credentials come only
from environment variables.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import smtplib
import sqlite3
import ssl
import time
from email.message import EmailMessage

REQUEST_PATH = "/api/v1/owner/email-otp/request"
VERIFY_PATH = "/api/v1/owner/email-otp/verify"
DEFAULT_OWNER_EMAIL = "mehmetcerdik457@gmail.com"
CODE_TTL = 600
MAX_ATTEMPTS = 5
MAX_REQUESTS = 3
REQUEST_WINDOW = 600
EMAIL = re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]{1,63}(\.[A-Za-z0-9-]{1,63}){1,5}")
CHALLENGE = re.compile(r"[A-Za-z0-9_-]{16,128}")
CODE = re.compile(r"[0-9]{6}")


class OtpDenied(Exception):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code = code
        self.status = status


def owner_email():
    return os.getenv("KRAL_OTP_OWNER_EMAIL", DEFAULT_OWNER_EMAIL).strip().lower()


def smtp_configured():
    return all(os.getenv(k, "").strip() for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"))


def send_via_smtp(to_address, code):
    """Send through the SMTP server named by env vars (STARTTLS by default)."""
    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    message = EmailMessage()
    message["Subject"] = "KRAL Genesis onay kodu"
    message["From"] = os.getenv("SMTP_FROM", "").strip() or user
    message["To"] = to_address
    message.set_content(
        f"KRAL Genesis giriş kodun: {code}\n\n"
        f"Kod {CODE_TTL // 60} dakika geçerlidir ve tek kullanımlıktır. "
        "Bu isteği sen yapmadıysan görmezden gel.")
    context = ssl.create_default_context()
    implicit_tls = os.getenv("SMTP_SSL", "").strip().lower() in ("1", "true", "yes")
    if implicit_tls:
        client = smtplib.SMTP_SSL(host, port, timeout=15, context=context)
    else:
        client = smtplib.SMTP(host, port, timeout=15)
    with client:
        if not implicit_tls:
            client.starttls(context=context)
        client.login(user, password)
        client.send_message(message)


class EmailOtp:
    def __init__(self, db_path, sender=None, clock=time.time):
        self.db_path = db_path
        self.sender = sender or send_via_smtp
        self.clock = clock
        secret = os.getenv("KRAL_OTP_SECRET", "").encode()
        self._pepper = secret or secrets.token_bytes(32)
        self._persistent_secret = len(secret.strip()) >= 32
        with self._db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS email_otp_v1 ("
                       "id TEXT PRIMARY KEY, digest TEXT NOT NULL, expires INTEGER NOT NULL, "
                       "attempts INTEGER NOT NULL DEFAULT 0, used INTEGER NOT NULL DEFAULT 0, "
                       "created INTEGER NOT NULL)")

    def _db(self):
        db = sqlite3.connect(self.db_path, timeout=3)
        db.execute("PRAGMA busy_timeout=3000")
        return db

    def _digest(self, challenge_id, code):
        return hmac.new(self._pepper, f"{challenge_id}:{code}".encode(), hashlib.sha256).hexdigest()

    def request(self, data):
        address = data.get("email")
        if not isinstance(address, str) or not EMAIL.fullmatch(address) or len(address) > 254:
            raise OtpDenied("EMAIL_INVALID")
        if address.strip().lower() != owner_email():
            raise OtpDenied("OTP_NOT_ALLOWED", 403)
        if not smtp_configured() and self.sender is send_via_smtp:
            raise OtpDenied("EMAIL_SERVICE_NOT_CONFIGURED", 503)
        # Real SMTP challenges must remain verifiable across process restarts and
        # workers. The random fallback is only useful for injected test senders.
        if self.sender is send_via_smtp and not self._persistent_secret:
            raise OtpDenied("EMAIL_SERVICE_NOT_CONFIGURED", 503)
        now = int(self.clock())
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM email_otp_v1 WHERE expires < ?", (now - 3600,))
            recent = db.execute("SELECT COUNT(*) FROM email_otp_v1 WHERE created > ?",
                                (now - REQUEST_WINDOW,)).fetchone()[0]
            if recent >= MAX_REQUESTS:
                raise OtpDenied("OTP_RATE_LIMITED", 429)
            challenge_id = secrets.token_urlsafe(24)
            code = f"{secrets.randbelow(1_000_000):06d}"
            db.execute("INSERT INTO email_otp_v1(id,digest,expires,created) VALUES(?,?,?,?)",
                       (challenge_id, self._digest(challenge_id, code), now + CODE_TTL, now))
            try:
                self.sender(owner_email(), code)
            except Exception:
                # Keep an unusable record so an unavailable SMTP service cannot
                # be hammered indefinitely by unauthenticated request retries.
                db.execute("UPDATE email_otp_v1 SET used=1 WHERE id=?", (challenge_id,))
                db.commit()
                raise OtpDenied("EMAIL_SEND_FAILED", 502)
        return {"challenge_id": challenge_id, "expires_in": CODE_TTL}

    def verify(self, data):
        challenge_id, code = data.get("challenge_id"), data.get("code")
        if (not isinstance(challenge_id, str) or not CHALLENGE.fullmatch(challenge_id)
                or not isinstance(code, str) or not CODE.fullmatch(code)):
            raise OtpDenied("OTP_INVALID")
        now = int(self.clock())
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT digest,expires,attempts,used FROM email_otp_v1 WHERE id=?",
                             (challenge_id,)).fetchone()
            if row is None or row[3] or row[1] <= now or row[2] >= MAX_ATTEMPTS:
                raise OtpDenied("OTP_DENIED", 403)
            if not hmac.compare_digest(row[0], self._digest(challenge_id, code)):
                db.execute("UPDATE email_otp_v1 SET attempts=attempts+1 WHERE id=?", (challenge_id,))
                db.commit()
                raise OtpDenied("OTP_DENIED", 403)
            db.execute("UPDATE email_otp_v1 SET used=1 WHERE id=?", (challenge_id,))
        return {"verified": True}
