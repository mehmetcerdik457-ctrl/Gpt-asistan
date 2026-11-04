"""Full local execution capacity cannot leave a paid chat request queued."""
import hashlib
import http.client
import os
import tempfile
import threading
import time
import unittest
import uuid
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from server import gateway as g, idempotency, owner_auth_v1 as auth
from server.tests.test_gateway import SyntheticProvider, b64, der


class ChatCapacityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.owner = ec.generate_private_key(ec.SECP256R1())
        self.device = ec.generate_private_key(ec.SECP256R1())
        self.device_id = hashlib.sha256(der(self.device)).hexdigest()
        self.env = patch.dict(os.environ, {
            "OMEGA_OWNER_ID": "owner-capacity", "OMEGA_DEVICE_ID": self.device_id,
            "OMEGA_OWNER_PUBLIC_DER_B64": b64(der(self.owner)),
            "OMEGA_DEVICE_PUBLIC_DER_B64": b64(der(self.device)),
            "OMEGA_NONCE_DB": self.tmp.name + "/nonces.sqlite3",
        })
        self.env.start()
        self.provider = SyntheticProvider()
        self.store = g.Store(self.tmp.name + "/gateway.sqlite3")
        self.gateway = g.Gateway(self.store, self.provider)
        self.gateway.models[self.provider.actual] = (
            {"id": self.provider.actual, "provider": self.provider.name,
             "verified_at": int(time.time()), "latency_ms": 1}, "synthetic-alias")
        self.held = 0
        self.threads = []

    def tearDown(self):
        self.release_slots()
        for thread in self.threads:
            thread.join(timeout=3)
        self.gateway.tasks.close()
        self.env.stop()
        self.tmp.cleanup()

    def hold_slots(self):
        for _ in range(4):
            self.assertTrue(self.gateway.execution_slots.acquire(blocking=False))
            self.held += 1

    def release_slots(self):
        while self.held:
            self.gateway.execution_slots.release()
            self.held -= 1

    def data(self, *, memory=False, key="capacity-idempotency-001"):
        return {"message": "Synthetic capacity request", "model": self.provider.actual,
                "include_memory": memory, "idempotency_key": key}

    def ledger_state(self, key):
        with self.store.connect() as db:
            return db.execute("SELECT state FROM idempotency_ledger WHERE key_sha256=?",
                              (idempotency.key_digest(key),)).fetchone()[0]

    def run_in_thread(self, operation):
        done, result = threading.Event(), {}
        def run():
            try:
                result["value"] = operation()
            except Exception as exc:
                result["error"] = exc
            finally:
                done.set()
        thread = threading.Thread(target=run, daemon=True)
        self.threads.append(thread)
        thread.start()
        return done, result

    def signed(self, path, body):
        timestamp, nonce = str(int(time.time())), uuid.uuid4().hex
        canonical = auth.canonical("POST", path, body, timestamp, nonce, "owner-capacity", self.device_id)
        return {"Content-Type": "application/json", "X-Omega-Owner-Id": "owner-capacity",
                "X-Omega-Device-Id": self.device_id, "X-Omega-Timestamp": timestamp,
                "X-Omega-Nonce": nonce,
                "X-Omega-Owner-Proof": b64(self.owner.sign(canonical, ec.ECDSA(hashes.SHA256()))),
                "X-Omega-Device-Proof": b64(self.device.sign(canonical, ec.ECDSA(hashes.SHA256())))}

    def test_busy_chat_returns_before_capacity_frees_and_allows_explicit_retry(self):
        data = self.data(memory=True)
        self.hold_slots()
        with patch.object(self.store, "recall", return_value=[{"text": "synthetic memory"}]) as recall:
            done, result = self.run_in_thread(lambda: self.gateway.chat(data))
            try:
                returned_while_busy = done.wait(0.3)
                calls_while_busy = len(self.provider.calls)
                recalls_while_busy = recall.call_count
            finally:
                self.release_slots()
            self.assertTrue(done.wait(2))
            self.assertTrue(returned_while_busy, "chat waited for a provider execution slot")
            error = result.get("error")
            self.assertIsInstance(error, g.Denied)
            self.assertEqual((error.code, error.status), ("OWNER_REQUEST_BUSY", 429))
            self.assertTrue(error.retryable)
            self.assertEqual(error.retry_after_seconds, 1)
            self.assertEqual((calls_while_busy, recalls_while_busy), (0, 0))
            self.assertEqual(self.ledger_state(data["idempotency_key"]), "failed")
            self.assertIn(self.provider.actual, self.gateway.models)
            self.assertEqual(self.gateway.chat(data)["text"], self.provider.answer)
        self.assertEqual(len(self.provider.calls), 1)

    def test_memory_preparation_deadline_prevents_dispatch_and_allows_explicit_retry(self):
        data = self.data(memory=True)
        now = [100.0]
        def slow_recall(*_, **__):
            now[0] += 9
            return [{"text": "synthetic memory"}]
        with patch.object(g.time, "monotonic", side_effect=lambda: now[0]), \
             patch.object(self.store, "recall", side_effect=slow_recall):
            with self.assertRaises(g.Denied) as denied:
                self.gateway.chat(data)
        self.assertEqual((denied.exception.code, denied.exception.status), ("CHAT_PREPARATION_TIMEOUT", 503))
        self.assertTrue(denied.exception.retryable)
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.ledger_state(data["idempotency_key"]), "failed")
        self.assertIn(self.provider.actual, self.gateway.models)
        with patch.object(self.store, "recall", return_value=[{"text": "synthetic memory"}]):
            self.assertEqual(self.gateway.chat(data)["text"], self.provider.answer)
        self.assertEqual(len(self.provider.calls), 1)
        # A timeout must also release the capacity it reserved.
        self.hold_slots()
        self.release_slots()

    def test_completed_idempotent_result_is_available_while_all_slots_busy(self):
        data = self.data()
        completed = self.gateway.chat(data)
        self.hold_slots()
        done, result = self.run_in_thread(lambda: self.gateway.chat(data))
        try:
            returned_while_busy = done.wait(0.3)
        finally:
            self.release_slots()
        self.assertTrue(done.wait(2))
        self.assertTrue(returned_while_busy)
        self.assertEqual(result, {"value": completed})
        self.assertEqual(len(self.provider.calls), 1)

    def test_disconnected_signed_http_client_cannot_leave_a_delayed_provider_post(self):
        processed = threading.Event()
        entered = threading.Event()
        real_chat = self.gateway.chat
        def observed_chat(data, **options):
            entered.set()
            try:
                return real_chat(data, **options)
            finally:
                processed.set()
        base = g.handler_for(self.gateway)
        class DisconnectedClientHandler(base):
            def send_json(self, status, data):
                try:
                    super().send_json(status, data)
                except (BrokenPipeError, ConnectionResetError):
                    pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), DisconnectedClientHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        data = self.data(key="http-disconnected-capacity-001")
        body, path = g.json_bytes(data), g.PREFIX + "chat"
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=0.1)
        self.hold_slots()
        try:
            with patch.object(self.gateway, "chat", side_effect=observed_chat):
                connection.request("POST", path, body=body, headers=self.signed(path, body))
                connection.close()
                self.assertTrue(entered.wait(1), "signed HTTP request did not reach chat")
                processed_before_release = processed.wait(0.3)
                self.release_slots()
                self.assertTrue(processed.wait(2))
            self.assertTrue(processed_before_release, "disconnected client left its chat waiting for capacity")
            self.assertEqual(self.provider.calls, [])
            self.assertEqual(self.ledger_state(data["idempotency_key"]), "failed")
            self.assertIn(self.provider.actual, self.gateway.models)
        finally:
            connection.close()
            self.release_slots()
            server.shutdown()
            server.server_close()
            server_thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
