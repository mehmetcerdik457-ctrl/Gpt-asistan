"""Synthetic model probes must respect capacity and the caller's dispatch budget."""
import tempfile
import threading
import unittest
from unittest.mock import patch

from server import gateway as g


class ProbeProvider:
    name = "synthetic"

    def __init__(self):
        self.calls = []
        self.aliases = ("alias-one",)

    def configured(self):
        return True

    def candidates(self):
        return self.aliases

    def reply(self, candidate, message, *, probe=False):
        self.calls.append(candidate)
        return "synthetic answer", "snapshot-" + candidate, 1


class ModelProbeCapacityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.provider = ProbeProvider()
        self.gateway = g.Gateway(g.Store(self.tmp.name + "/gateway.sqlite3"), self.provider)
        self.held = 0
        self.threads = []

    def tearDown(self):
        self.release_slots()
        for thread in self.threads:
            thread.join(timeout=3)
        self.gateway.tasks.close()
        self.tmp.cleanup()

    def hold_slots(self):
        for _ in range(4):
            self.assertTrue(self.gateway.execution_slots.acquire(blocking=False))
            self.held += 1

    def release_slots(self):
        while self.held:
            self.gateway.execution_slots.release()
            self.held -= 1

    def test_models_route_honors_expired_inherited_deadline_without_provider_post(self):
        with patch.object(g.time, "monotonic", return_value=100.0):
            expired = self.gateway.route(g.PREFIX + "models", {}, request_deadline=99.0)
            self.assertEqual(expired, {"models": [], "errors": [{"code": "MODEL_PROBE_TIMEOUT"}]})
            self.assertEqual(self.provider.calls, [])
            # No POST happened, so a later explicit refresh can try immediately.
            recovered = self.gateway.verified_models(deadline=101.0)
        self.assertEqual([model["id"] for model in recovered["models"]], ["snapshot-alias-one"])
        self.assertEqual(self.provider.calls, ["alias-one"])

    def test_full_execution_capacity_returns_busy_without_queuing_a_probe(self):
        done, result = threading.Event(), {}
        def refresh():
            try:
                result["value"] = self.gateway.verified_models()
            except Exception as exc:
                result["error"] = exc
            finally:
                done.set()
        self.hold_slots()
        thread = threading.Thread(target=refresh, daemon=True)
        self.threads.append(thread)
        thread.start()
        try:
            returned_while_busy = done.wait(0.3)
        finally:
            self.release_slots()
        self.assertTrue(done.wait(2))
        self.assertTrue(returned_while_busy, "model probe waited behind occupied provider slots")
        self.assertEqual(result, {"value": {"models": [], "errors": [{"code": "OWNER_REQUEST_BUSY"}]}})
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(len(self.gateway.verified_models()["models"]), 1)
        self.assertEqual(self.provider.calls, ["alias-one"])

    def test_second_probe_wave_dispatches_only_within_remaining_request_budget(self):
        for elapsed, expected_posts in ((12.0, 4), (21.0, 2)):
            with self.subTest(first_wave_seconds=elapsed):
                clock = [100.0]
                class TwoWaveProvider(ProbeProvider):
                    def __init__(self):
                        super().__init__()
                        self.aliases = tuple("alias-" + str(i) for i in range(4))
                        self.lock = threading.Lock()
                        self.wave = threading.Barrier(2)

                    def reply(self, candidate, message, *, probe=False):
                        with self.lock:
                            self.calls.append(candidate)
                        # Both first-wave POSTs enter before either response
                        # advances time. The second case simulates an overrun
                        # beyond the fixed upstream timeout to test the guard.
                        self.wave.wait(timeout=2)
                        with self.lock:
                            clock[0] = 100.0 + elapsed
                        return "synthetic answer", "snapshot-" + candidate, 1
                provider = TwoWaveProvider()
                self.gateway.provider = provider
                with patch.object(g.time, "monotonic", side_effect=lambda: clock[0]):
                    result = self.gateway.verified_models()
                expected_aliases = {"alias-" + str(i) for i in range(expected_posts)}
                self.assertEqual(set(provider.calls), expected_aliases)
                self.assertEqual(len(provider.calls), expected_posts)
                self.assertEqual({model["id"] for model in result["models"]},
                                 {"snapshot-" + alias for alias in expected_aliases})
                self.assertEqual(result["errors"], [{"code": "MODEL_PROBE_TIMEOUT"}] * (4 - expected_posts))
                self.hold_slots()
                self.release_slots()


if __name__ == "__main__":
    unittest.main()
