"""OMEGA Owner v1: dual P-256 signature gate. No enrollment on this public endpoint."""
import base64
import hashlib
import os
import re
import sqlite3
import time
from .secure_sqlite import secure_sqlite_file

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
except ImportError:
    InvalidSignature = None
    hashes = serialization = ec = None

PATH = "/api/v1/owner/chat"
REQUIRED = ("X-Omega-Owner-Id", "X-Omega-Device-Id", "X-Omega-Timestamp",
            "X-Omega-Nonce", "X-Omega-Owner-Proof", "X-Omega-Device-Proof")


def _decode(s):
    if not isinstance(s, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,4096}", s):
        raise ValueError("BAD_ENCODING")
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def configured():
    needed = ("OMEGA_OWNER_ID", "OMEGA_DEVICE_ID",
              "OMEGA_OWNER_PUBLIC_DER_B64", "OMEGA_DEVICE_PUBLIC_DER_B64",
              "OMEGA_NONCE_DB")
    return ec is not None and all(os.getenv(k, "").strip() for k in needed)


def _key(var):
    key = serialization.load_der_public_key(_decode(os.environ[var]))
    if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
        raise ValueError("WRONG_KEY")
    return key


def canonical(method, path, raw, timestamp, nonce, owner, device):
    """Bind both identities, exact bytes, URL and a bounded timestamp."""
    return ("\n".join(("OMEGA-OWNER-API-V1", method, path,
                      hashlib.sha256(raw).hexdigest(), str(timestamp),
                      nonce, owner, device))).encode("utf-8")


def authorize(headers, raw, method="POST", path=PATH, now=None):
    """Return a fixed error; never log/request-key material or reveal internals."""
    if not configured():
        return False, "OWNER_IDENTITY_NOT_PROVISIONED"
    try:
        if not isinstance(raw, bytes) or not 0 < len(raw) <= 65536:
            return False, "OWNER_BODY_DENIED"
        owner_key = _key("OMEGA_OWNER_PUBLIC_DER_B64")
        device_key = _key("OMEGA_DEVICE_PUBLIC_DER_B64")
        owner_der = owner_key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        device_der = device_key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        if owner_der == device_der or hashlib.sha256(device_der).hexdigest() != os.environ["OMEGA_DEVICE_ID"]:
            return False, "OWNER_IDENTITY_NOT_PROVISIONED"
        h = {name: headers.get(name, "") for name in REQUIRED}
        if not all(isinstance(v, str) and v for v in h.values()):
            return False, "OWNER_AUTH_REQUIRED"
        owner, device = h["X-Omega-Owner-Id"], h["X-Omega-Device-Id"]
        # Match the Android signed envelope exactly; do not accept alternate IDs.
        if (not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", owner)
            or not re.fullmatch(r"[a-f0-9]{64}", device)):
            return False, "OWNER_IDENTITY_DENIED"
        if owner != os.environ["OMEGA_OWNER_ID"] or device != os.environ["OMEGA_DEVICE_ID"]:
            return False, "OWNER_IDENTITY_DENIED"
        ts = h["X-Omega-Timestamp"]
        if not re.fullmatch(r"[0-9]{10}", ts):
            return False, "OWNER_AUTH_EXPIRED"
        now = int(time.time() if now is None else now)
        if abs(now - int(ts)) > 30:
            return False, "OWNER_AUTH_EXPIRED"
        nonce = h["X-Omega-Nonce"]
        if not re.fullmatch(r"[a-f0-9]{32,64}", nonce):
            return False, "OWNER_AUTH_REQUIRED"
        msg = canonical(method, path, raw, ts, nonce, owner, device)
        owner_key.verify(
            _decode(h["X-Omega-Owner-Proof"]), msg, ec.ECDSA(hashes.SHA256()))
        device_key.verify(
            _decode(h["X-Omega-Device-Proof"]), msg, ec.ECDSA(hashes.SHA256()))
        db_path = secure_sqlite_file(os.environ["OMEGA_NONCE_DB"])
        # Never trust in-process caches for replay protection; transaction + unique PK.
        with sqlite3.connect(db_path, timeout=3) as db:
            db.execute("PRAGMA busy_timeout=3000")
            db.execute("CREATE TABLE IF NOT EXISTS owner_nonce_v1 (nonce TEXT PRIMARY KEY, seen_at INTEGER NOT NULL)")
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM owner_nonce_v1 WHERE seen_at < ?", (now - 90,))
            db.execute("INSERT INTO owner_nonce_v1(nonce, seen_at) VALUES(?,?)", (nonce, now))
        return True, "OWNER_AUTH_VERIFIED"
    except sqlite3.Error:
        return False, "OWNER_AUTH_REPLAY_OR_STORAGE_DENIED"
    except Exception:
        # Signature, decoding, and KeyStore provisioning failures stay fail closed.
        return False, "OWNER_AUTH_DENIED"
