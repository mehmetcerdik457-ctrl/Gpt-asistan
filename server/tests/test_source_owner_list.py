"""Tests for bounded source browsing under a signed Owner-only gateway."""
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

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from server import owner_auth_v1 as auth
from server.gateway import BoundedThreadingHTTPServer, Gateway, Store, handler_for, Denied
from server.source_owner_list import list_sources
from server.source_owner_tool import SourceInspectionDenied


def b64(data):
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


class NoProvider:
    name = "offline-only"

    def configured(self):
        return False

    def reply(self, *_args, **_kwargs):
        raise AssertionError("Listing must never contact AI")


class SourceListTests(unittest.TestCase):
    def test_files_and_nested_candidates_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "models").mkdir()
            (root / "models" / "owned.gguf").write_bytes(b"model fixture")
            (root / "a.apk").write_bytes(b"APK fixture")
            (root / "notes.txt").write_text("not supported")
            (root / ".hidden.apk").write_bytes(b"secret")
            (root / "secrets").mkdir()
            (root / "secrets" / "credentials.json").write_text("{}")
            (root / "google-services.json").write_text("{}")
            (root / "external").symlink_to(root / "models", target_is_directory=True)
            (root / "key.apk").symlink_to(root / "a.apk")
            data = list_sources(tmp)
            self.assertEqual([x["source_id"] for x in data["sources"]],
                             ["a.apk", "models/owned.gguf"])
            self.assertTrue(data["read_only"])
            self.assertEqual(data["capability_status"], "UNTESTED")
            self.assertEqual(data["integration_status"], "NOT_CONNECTED")
            self.assertEqual((root / "a.apk").read_bytes(), b"APK fixture")

    def test_file_and_visit_caps_are_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(6):
                (Path(tmp) / f"candidate{i}.apk").write_bytes(b"x")
            data = list_sources(tmp, max_files=2)
            self.assertEqual(len(data["sources"]), 2)
            self.assertTrue(data["truncated"])
            limited = list_sources(tmp, max_entries=1)
            self.assertEqual(len(limited["sources"]), 1)
            self.assertTrue(limited["truncated"])

    def test_oversize_and_depth_skip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "large.apk").write_bytes(b"x" * 8)
            (root / "small.apk").write_bytes(b"x")
            deep = root / "one" / "two" / "three" / "four"
            deep.mkdir(parents=True)
            (deep / "hidden.apk").write_bytes(b"x")
            data = list_sources(tmp, max_file_bytes=4)
            ids = {x["source_id"] for x in data["sources"]}
            self.assertNotIn("large.apk", ids)
            self.assertIn("small.apk", ids)
            self.assertNotIn("one/two/three/four/hidden.apk", ids)

    def test_root_missing_and_invalid_limits_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            for root in ("", "/not-existing-kral-source-folder-xyz"):
                with self.assertRaises(SourceInspectionDenied):
                    list_sources(root)
            for opts in ({"max_files": 0}, {"max_files": True},
                         {"max_entries": 501}, {"max_depth": 4},
                         {"max_file_bytes": -1}):
                with self.subTest(opts=opts):
                    with self.assertRaises(SourceInspectionDenied):
                        list_sources(tmp, **opts)

    def test_gateway_off_by_default_and_unknown_fields_denied(self):
        gateway = Gateway(object(), provider=NoProvider())
        with patch.dict(os.environ, {"KRAL_SOURCE_ROOT": ""}):
            with self.assertRaises(Denied):
                gateway.route("/api/v1/owner/sources", {"action": "list"})
        for data in ({"action": "list", "root": "/tmp"},
                     {"action": "list", "source_id": "a.apk"},
                     {"action": "delete"}):
            with self.subTest(data=data):
                with self.assertRaises(Denied) as ctx:
                    gateway.route("/api/v1/owner/sources", data)
                self.assertEqual(ctx.exception.code, "SOURCE_FIELDS_DENIED")

    def test_signed_http_list_and_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sample.apk").write_bytes(b"not-executed")
            private_owner = ec.generate_private_key(ec.SECP256R1())
            private_device = ec.generate_private_key(ec.SECP256R1())
            pub_owner = private_owner.public_key().public_bytes(
                serialization.Encoding.DER,
                serialization.PublicFormat.SubjectPublicKeyInfo)
            pub_device = private_device.public_key().public_bytes(
                serialization.Encoding.DER,
                serialization.PublicFormat.SubjectPublicKeyInfo)
            owner_id = "list-test-owner"
            device_id = hashlib.sha256(pub_device).hexdigest()
            path = "/api/v1/owner/sources"
            body = b'{"action":"list"}'
            timestamp = str(int(time.time()))
            nonce = secrets.token_hex(24)
            signature = auth.canonical("POST", path, body, timestamp, nonce,
                                        owner_id, device_id)
            env = {
                "OMEGA_OWNER_ID": owner_id,
                "OMEGA_DEVICE_ID": device_id,
                "OMEGA_OWNER_PUBLIC_DER_B64": b64(pub_owner),
                "OMEGA_DEVICE_PUBLIC_DER_B64": b64(pub_device),
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
                "X-Omega-Owner-Proof": b64(private_owner.sign(
                    signature, ec.ECDSA(hashes.SHA256()))),
                "X-Omega-Device-Proof": b64(private_device.sign(
                    signature, ec.ECDSA(hashes.SHA256()))),
            }
            with patch.dict(os.environ, env):
                server = BoundedThreadingHTTPServer(
                    ("127.0.0.1", 0),
                    handler_for(Gateway(Store(env["OMEGA_DATA_DB"]),
                                        provider=NoProvider())),
                    max_workers=2)
                runner = threading.Thread(target=server.serve_forever, daemon=True)
                runner.start()
                try:
                    def request(custom_headers):
                        conn = http.client.HTTPConnection(
                            "127.0.0.1", server.server_port, timeout=5)
                        try:
                            conn.request("POST", path, body, custom_headers)
                            result = conn.getresponse()
                            return result.status, json.loads(result.read())
                        finally:
                            conn.close()

                    unsigned, _ = request({"Content-Type": "application/json"})
                    self.assertEqual(unsigned, 403)
                    status, response = request(headers)
                    self.assertEqual(status, 200, response)
                    self.assertEqual(response["sources"][0]["source_id"], "sample.apk")
                    self.assertEqual(response["sources"][0]["format_hint"], "android_apk")
                    self.assertTrue(response["read_only"])
                    self.assertEqual(response["capability_status"], "UNTESTED")
                    replay_status, _ = request(headers)
                    self.assertEqual(replay_status, 403)
                finally:
                    server.shutdown()
                    server.server_close()
                    runner.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
