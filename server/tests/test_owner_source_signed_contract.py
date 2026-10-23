"""Real loopback HTTP contract with temporary test identities, never Owner keys."""
import base64
import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from server import owner_auth_v1 as auth
from server.gateway import BoundedThreadingHTTPServer, Gateway, Store, handler_for


def encoded(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


class NoLiveProvider:
    name = "offline-test"
    def configured(self):
        return False
    def reply(self, *_args, **_kwargs):
        raise AssertionError("HTTP source inspection must not call AI")


class SignedSourceHTTPTests(unittest.TestCase):
    def test_signed_owner_source_inspection_then_replay_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            apk = root / "sample.apk"
            with ZipFile(apk, "w") as z:
                z.writestr("AndroidManifest.xml", b"fixture, not installable")
                z.writestr("classes.dex", b"fixture")
            apk_bytes_before = apk.read_bytes()
            owner_private = ec.generate_private_key(ec.SECP256R1())
            device_private = ec.generate_private_key(ec.SECP256R1())
            owner_der = owner_private.public_key().public_bytes(
                serialization.Encoding.DER,
                serialization.PublicFormat.SubjectPublicKeyInfo)
            device_der = device_private.public_key().public_bytes(
                serialization.Encoding.DER,
                serialization.PublicFormat.SubjectPublicKeyInfo)
            owner_id = "offline-ci-owner"
            device_id = hashlib.sha256(device_der).hexdigest()
            path = "/api/v1/owner/sources"
            body = json.dumps({"action": "inspect", "source_id": "sample.apk"},
                              separators=(",", ":")).encode()
            timestamp = str(int(time.time()))
            nonce = secrets.token_hex(16)
            signed = auth.canonical("POST", path, body, timestamp, nonce,
                                    owner_id, device_id)
            env = {
                "OMEGA_OWNER_ID": owner_id,
                "OMEGA_DEVICE_ID": device_id,
                "OMEGA_OWNER_PUBLIC_DER_B64": encoded(owner_der),
                "OMEGA_DEVICE_PUBLIC_DER_B64": encoded(device_der),
                "OMEGA_NONCE_DB": str(root / "nonce.sqlite3"),
                "OMEGA_DATA_DB": str(root / "data.sqlite3"),
                "KRAL_SOURCE_ROOT": str(root),
            }
            headers = {
                "Content-Type": "application/json",
                "X-Omega-Owner-Id": owner_id,
                "X-Omega-Device-Id": device_id,
                "X-Omega-Timestamp": timestamp,
                "X-Omega-Nonce": nonce,
                "X-Omega-Owner-Proof": encoded(owner_private.sign(
                    signed, ec.ECDSA(hashes.SHA256()))),
                "X-Omega-Device-Proof": encoded(device_private.sign(
                    signed, ec.ECDSA(hashes.SHA256()))),
            }
            with patch.dict(os.environ, env, clear=False):
                gateway = Gateway(Store(env["OMEGA_DATA_DB"]),
                                  provider=NoLiveProvider())
                server = BoundedThreadingHTTPServer(
                    ("127.0.0.1", 0), handler_for(gateway), max_workers=2)
                runner = threading.Thread(target=server.serve_forever, daemon=True)
                runner.start()
                try:
                    def request():
                        client = http.client.HTTPConnection(
                            "127.0.0.1", server.server_port, timeout=5)
                        try:
                            client.request("POST", path, body, headers)
                            response = client.getresponse()
                            return response.status, json.loads(response.read())
                        finally:
                            client.close()

                    status, document = request()
                    self.assertEqual(status, 200, document)
                    source = document["source"]
                    self.assertEqual(source["status"], "ANALYZED_STATIC")
                    self.assertEqual(source["sha256"],
                                     hashlib.sha256(apk_bytes_before).hexdigest())
                    self.assertEqual(source["apk_structure"]["dex_count"], 1)
                    self.assertEqual(source["integration_status"], "NOT_CONNECTED")
                    self.assertEqual(apk.read_bytes(), apk_bytes_before)

                    replay_status, replay = request()
                    self.assertEqual(replay_status, 403, replay)
                    self.assertEqual(replay.get("error"),
                                     "OWNER_AUTH_REPLAY_OR_STORAGE_DENIED")
                finally:
                    server.shutdown()
                    server.server_close()
                    runner.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
