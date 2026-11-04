"""Deterministic registry/worker races using synthetic upstreams only."""
import tempfile
import threading
import time
import unittest

from server import gateway as g, owner_workers


class ProbeProvider:
    name = "synthetic"

    def __init__(self):
        self.available = True
        self.alias = "alias-old"
        self.calls = []
        self.entered = threading.Event()
        self.release = threading.Event()
        self.block_old = False

    def configured(self):
        return self.available

    def candidates(self):
        return (self.alias,)

    def reply(self, candidate, message, *, probe=False):
        self.calls.append((candidate, probe))
        if self.block_old and candidate == "alias-old":
            self.entered.set()
            if not self.release.wait(4):
                raise AssertionError("synthetic probe was not released")
        return "synthetic answer", "snapshot-" + candidate, 1


class GatedWorkerSlots:
    """Hold four worker slots and bound cleanup if old probes wait for them."""
    def __init__(self):
        self.slots = threading.BoundedSemaphore(4)
        self.lock = threading.Lock()
        self.entered = 0
        self.all_workers_entered = threading.Event()
        self.release_workers = threading.Event()
        self.probe_attempted = threading.Event()

    def acquire(self, blocking=True, timeout=-1):
        with self.lock:
            self.entered += 1
            position = self.entered
        if position > 4:
            self.probe_attempted.set()
        acquired = (self.slots.acquire(timeout=2 if timeout == -1 else timeout) if blocking
                    else self.slots.acquire(blocking=False))
        if not acquired:
            return False
        if position <= 4:
            if position == 4:
                self.all_workers_entered.set()
            if not self.release_workers.wait(4):
                self.slots.release()
                raise AssertionError("synthetic workers were not released")
        return True

    def release(self):
        self.slots.release()

    def __enter__(self):
        if not self.acquire():
            raise AssertionError("probe deadlocked behind model-cache workers")
        return self

    def __exit__(self, *_):
        self.release()


class GatewayConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.provider = ProbeProvider()
        self.gateway = g.Gateway(g.Store(self.tmp.name + "/gateway.sqlite3"), self.provider)
        self.threads = []

    def tearDown(self):
        self.provider.release.set()
        for thread, _ in self.threads:
            thread.join(timeout=5)
        self.gateway.tasks.close()
        self.tmp.cleanup()

    def start(self, operation):
        result = {}
        def run():
            try:
                result["value"] = operation()
            except BaseException as exc:
                result["error"] = exc
        thread = threading.Thread(target=run, daemon=True)
        self.threads.append((thread, result))
        thread.start()
        return thread, result

    def finished(self, item):
        thread, result = item
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive(), "gateway operation did not finish")
        self.assertNotIn("error", result, repr(result.get("error")))
        return result["value"]

    def test_cached_model_workers_and_busy_probe_cannot_invert_locks(self):
        slots = GatedWorkerSlots()
        self.gateway.execution_slots = slots
        self.gateway.models = {
            "snapshot-cached": ({"id": "snapshot-cached", "provider": "synthetic",
                                  "verified_at": int(time.time()), "latency_ms": 1}, "cached")
        }
        payload = {"max_parallel": 4, "tasks": [
            {"id": f"W{i:02d}", "kind": "models.cached", "args": {}} for i in range(1, 5)
        ]}
        workers = self.start(lambda: owner_workers.run_batch(self.gateway, payload))
        refresh = None
        registry_unlocked = False
        try:
            self.assertTrue(slots.all_workers_entered.wait(2))
            refresh = self.start(self.gateway.verified_models)
            self.assertTrue(slots.probe_attempted.wait(2))
            registry_unlocked = self.gateway.lock.acquire(timeout=0.25)
            if registry_unlocked:
                self.gateway.lock.release()
        finally:
            slots.release_workers.set()
        worker_result = self.finished(workers)
        if refresh is not None:
            probe_result = self.finished(refresh)
            self.assertEqual(probe_result["errors"], [{"code": "OWNER_REQUEST_BUSY"}])
        self.assertTrue(registry_unlocked, "model registry lock held while awaiting execution slots")
        self.assertTrue(all(row["status"] == "COMPLETED_LOCAL_READ" for row in worker_result["results"]))
        self.assertEqual(self.provider.calls, [])

    def test_same_configuration_uses_one_inflight_probe(self):
        self.provider.block_old = True
        first = self.start(self.gateway.verified_models)
        try:
            self.assertTrue(self.provider.entered.wait(2))
            others = [self.start(self.gateway.verified_models) for _ in range(4)]
            # A request for an active refresh reads the existing snapshot instead
            # of adding provider calls or holding the registry lock for network.
            for operation in others:
                operation[0].join(timeout=1)
            completed_without_network = all(not operation[0].is_alive() for operation in others)
        finally:
            self.provider.release.set()
        self.finished(first)
        for operation in others:
            self.finished(operation)
        self.assertTrue(completed_without_network)
        self.assertEqual(self.provider.calls, [("alias-old", True)])

    def test_invalidated_old_refresh_cannot_overwrite_new_configuration(self):
        self.provider.block_old = True
        old = self.start(self.gateway.verified_models)
        try:
            self.assertTrue(self.provider.entered.wait(2))
            self.provider.available = False
            disabled = self.start(self.gateway.verified_models)
            disabled[0].join(timeout=1)
            self.assertFalse(disabled[0].is_alive(), "configuration invalidation waited for old network call")
            self.assertEqual(self.finished(disabled)["models"], [])
            self.provider.alias = "alias-new"
            self.provider.available = True
            new = self.finished(self.start(self.gateway.verified_models))
            self.assertEqual([model["id"] for model in new["models"]], ["snapshot-alias-new"])
        finally:
            self.provider.release.set()
        self.finished(old)
        self.assertEqual(set(self.gateway.models), {"snapshot-alias-new"})
        self.assertEqual(self.provider.calls, [("alias-old", True), ("alias-new", True)])


if __name__ == "__main__":
    unittest.main()
