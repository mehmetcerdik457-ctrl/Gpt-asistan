"""Proof of signed local worker execution, WAL, idempotency and Sol preference.

Uses synthetic keys and model data; never contacts OpenAI or a real Android phone.
"""
import base64
import hashlib
import json
import os
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from server import gateway, idempotency, owner_auth_v1, owner_workers


def b64(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def der(key):
    return key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


class NeverCallProvider:
    name = "openai"
    def __init__(self):
        self.calls = 0
    def configured(self):
        return True
    def candidates(self):
        return ("gpt-5.6-sol",)
    def reply(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("PROVIDER_CALL_FORBIDDEN")


class OwnerWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.owner = ec.generate_private_key(ec.SECP256R1())
        self.device = ec.generate_private_key(ec.SECP256R1())
        identity = hashlib.sha256(der(self.device)).hexdigest()
        self.env = patch.dict(os.environ, {
            "OMEGA_OWNER_ID": "owner-fixture",
            "OMEGA_DEVICE_ID": identity,
            "OMEGA_OWNER_PUBLIC_DER_B64": b64(der(self.owner)),
            "OMEGA_DEVICE_PUBLIC_DER_B64": b64(der(self.device)),
            "OMEGA_NONCE_DB": str(Path(self.temp.name) / "nonces.sqlite3"),
        })
        self.env.start()
        self.provider = NeverCallProvider()
        self.store = gateway.Store(str(Path(self.temp.name) / "memory.sqlite3"))
        self.gateway = gateway.Gateway(self.store, self.provider)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), gateway.handler_for(self.gateway))
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:" + str(self.httpd.server_port)

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=3)
        self.env.stop()
        self.temp.cleanup()

    def signed_headers(self, raw, path):
        ts = str(int(time.time()))
        nonce = uuid.uuid4().hex
        msg = owner_auth_v1.canonical("POST", path, raw, ts, nonce,
                                     "owner-fixture", os.environ["OMEGA_DEVICE_ID"])
        return {
            "Content-Type": "application/json",
            "X-Omega-Owner-Id": "owner-fixture",
            "X-Omega-Device-Id": os.environ["OMEGA_DEVICE_ID"],
            "X-Omega-Timestamp": ts, "X-Omega-Nonce": nonce,
            "X-Omega-Owner-Proof": b64(self.owner.sign(msg, ec.ECDSA(hashes.SHA256()))),
            "X-Omega-Device-Proof": b64(self.device.sign(msg, ec.ECDSA(hashes.SHA256()))),
        }

    def post(self, data, headers=None):
        raw = gateway.json_bytes(data)
        route = "/api/v1/owner/workers"
        headers = headers if headers is not None else self.signed_headers(raw, route)
        req = urllib.request.Request(self.url + route, data=raw, method="POST", headers=headers)
        try:
            response = urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    @staticmethod
    def job(n, kind="status", args=None):
        return {"id": f"W{n:02d}", "kind": kind, "args": {} if args is None else args}

    def test_fifty_slots_use_four_local_threads_without_provider(self):
        payload = {"tasks": [self.job(i) for i in range(1, 51)], "max_parallel": 4}
        status, data = self.post(payload)
        self.assertEqual(status, 200)
        self.assertEqual((data["logical_worker_slots"], data["executed_tasks"]), (50, 50))
        self.assertEqual(data["parallel_limit"], 4)
        self.assertEqual((data["provider_calls"], data["external_actions"], data["automatic_approvals"]), (0, 0, 0))
        self.assertTrue(all(j["status"] == "COMPLETED_LOCAL_READ" for j in data["results"]))
        self.assertEqual(self.provider.calls, 0)
        self.assertEqual(len(data["task_sha256"]), 64)

    def test_signed_memory_search_and_wal_persistence(self):
        with self.store.connect() as db:
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        # Bind the empty store to the verified owner before inserting data.\n        # Pre-populated unbound stores MUST return HTTP 503, not be claimed silently.\n        status, _ = self.post({"tasks": [self.job(1)], "max_parallel": 1})\n        self.assertEqual(status, 200)\n        self.store.remember("Güvenli yerel hafıza kontrolü")
        payload = {"tasks": [self.job(1, "memory.search", {"query": "hafıza", "limit": 5})],
                   "max_parallel": 1}
        status, data = self.post(payload)
        self.assertEqual(status, 200)
        self.assertEqual(data["results"][0]["result"]["memories"][0]["text"], "Güvenli yerel hafıza kontrolü")
        self.assertEqual(self.provider.calls, 0)

    def test_missing_or_invalid_signature_denied_before_reads(self):
        payload = {"tasks": [self.job(1)], "max_parallel": 1}
        status, data = self.post(payload, headers={"Content-Type": "application/json"})
        self.assertEqual(status, 403)
        self.assertNotIn("results", data)
        self.assertEqual(self.provider.calls, 0)

    def test_unknown_write_tool_denied_as_entire_batch(self):
        payload = {"tasks": [self.job(1), self.job(2, "github.merge", {})],
                   "max_parallel": 2}
        status, data = self.post(payload)
        self.assertEqual((status, data["error"]), (400, "WORKER_REQUEST_DENIED"))
        self.assertEqual(self.provider.calls, 0)

    def test_duplicate_ids_and_excess_parallelism_denied(self):
        for payload in [
            {"tasks": [self.job(1), self.job(1)], "max_parallel": 2},
            {"tasks": [self.job(1)], "max_parallel": 50},
            {"tasks": [self.job(1)], "max_parallel": True},
            {"tasks": [self.job(51)], "max_parallel": 1},
        ]:
            with self.subTest(payload=payload):
                status, data = self.post(payload)
                self.assertEqual((status, data["error"]), (400, "WORKER_REQUEST_DENIED"))

    def test_replay_same_signed_worker_request_denied(self):
        payload = {"tasks": [self.job(1)], "max_parallel": 1}
        raw = gateway.json_bytes(payload)
        headers = self.signed_headers(raw, "/api/v1/owner/workers")
        self.assertEqual(self.post(payload, headers)[0], 200)
        self.assertEqual(self.post(payload, headers)[0], 403)

    def test_sha256_idempotency_replayed_after_new_connection(self):
        key = "owner-work-0001"
        digest = idempotency.request_digest({"message": "Merhaba", "model": "gpt-5.6-sol"})
        with self.store.connect() as db:
            self.assertIsNone(idempotency.reserve(db, key, digest))
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            idempotency.complete(db, key, digest, {"text": "once"})
        with self.store.connect() as db:
            self.assertEqual(idempotency.reserve(db, key, digest), {"text": "once"})
        with self.store.connect() as db:
            with self.assertRaises(ValueError):
                idempotency.reserve(db, key, idempotency.request_digest({"message": "changed"}))

    def test_model_preference_cannot_bypass_allowlist(self):
        with patch.dict(os.environ, {
            "OPENAI_ALLOWED_MODELS": "gpt-6-luna,gpt-5.6-sol",
            "OPENAI_MODEL_PREFERRED": "gpt-5.6-sol",
        }):
            self.assertEqual(gateway.OpenAIProvider().candidates(),
                             ("gpt-5.6-sol", "gpt-6-luna"))
        with patch.dict(os.environ, {
            "OPENAI_ALLOWED_MODELS": "gpt-6-luna",
            "OPENAI_MODEL_PREFERRED": "gpt-5.6-sol",
        }):
            self.assertEqual(gateway.OpenAIProvider().candidates(), ("gpt-6-luna",))
        with patch.dict(os.environ, {
            "OPENAI_ALLOWED_MODELS": "",
            "OPENAI_MODEL_PREFERRED": "gpt-5.6-sol",
        }):
            self.assertEqual(gateway.OpenAIProvider().candidates(), ())


if __name__ == "__main__":
    unittest.main()
