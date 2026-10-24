"""Actual localhost HTTP protocol tests, NOT downloaded model weight tests."""
import json
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from server import local_open_workers as w
from server import mission_control as mission

ROOT = Path(__file__).resolve().parents[2]


class FakeModels(BaseHTTPRequestHandler):
    requests = []
    mutex = threading.Lock()
    catalog = ["qwen3:1.7b", "gpt-oss:20b"]

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path != "/v1/models":
            self.send_error(404)
            return
        self.send_json({"data": [{"id": m} for m in self.catalog]})

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        try:
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        except (KeyError, ValueError):
            self.send_error(400)
            return
        with self.mutex:
            self.requests.append(payload)
        name = payload["messages"][0]["content"]
        self.send_json({
            "choices": [{"message": {"content": "Fixture answer from " + name[-90:]},
                         "finish_reason": "stop"}],
        })

    def send_json(self, value):
        raw = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class OpenWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeModels)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.provider = {
            "schema": 1,
            "endpoint": f"http://127.0.0.1:{cls.server.server_port}/v1",
            "model": "qwen3:1.7b",
            "supervisor_model": "gpt-oss:20b",
            "timeout_seconds": 10,
            "max_output_tokens": 150,
        }
        cls.repos = mission.validate_repository_inventory(
            mission.read_small_json(mission.REPO_INVENTORY, 16384))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def setUp(self):
        with FakeModels.mutex:
            FakeModels.requests.clear()

    def test_http_backend_catalog_and_real_responses(self):
        self.assertEqual(w.probe(self.provider),
                         {"qwen3:1.7b", "gpt-oss:20b"})
        out = w.infer(self.provider, "qwen3:1.7b", "code-reviewer",
                      "worker-01", "Inspect", "No shell", "mehmetcerdik457-ctrl/Gpt-asistan")
        self.assertIn("Fixture answer", out)
        self.assertEqual(len(FakeModels.requests), 1)
        req = FakeModels.requests[0]
        self.assertEqual(req["model"], "qwen3:1.7b")
        self.assertEqual(len(req["messages"]), 2)
        self.assertNotIn("tools", req)
        self.assertIn("worker-01", req["messages"][0]["content"])

    def test_run_real_first_wave_with_independent_supervisor_request(self):
        manifest = mission.read_small_json(ROOT / "missions/sample.json")
        result = w.run_wave(manifest, self.repos, self.provider, review=True)
        self.assertEqual(result["mode"], "LOCAL_INFERENCE_REQUESTS")
        self.assertEqual(len(result["responses"]), 3)
        self.assertEqual(result["pending_tasks"], 1)
        self.assertEqual(len(FakeModels.requests), 6)
        self.assertTrue(all(t["status"] == "MODEL_REVIEWED_AWAITING_REAL_TESTS"
                            for t in result["responses"]))
        self.assertEqual(result["completed_real_repository_tasks"], 0)
        self.assertTrue(result["next_wave_blocked_on_owner_verification"])
        self.assertEqual(result["copilot_credits_used"], 0)
        self.assertEqual(len({r["worker"] for r in result["responses"]}), 3)

    def test_fifty_distinct_worker_contexts_reach_real_local_http(self):
        def invoke(index):
            return w.infer(self.provider, "qwen3:1.7b",
                           mission.ROLES[index % len(mission.ROLES)],
                           f"worker-{index + 1:02d}",
                           "Inspect controlled source", f"Scope={index}",
                           "mehmetcerdik457-ctrl/Gpt-asistan")
        with ThreadPoolExecutor(max_workers=4) as pool:
            outputs = list(pool.map(invoke, range(50)))
        self.assertEqual(len(outputs), 50)
        self.assertEqual(len(FakeModels.requests), 50)
        systems = [r["messages"][0]["content"] for r in FakeModels.requests]
        self.assertEqual(len(set(systems)), 50)
        self.assertTrue(all("tools" not in r for r in FakeModels.requests))
        self.assertTrue(all("Fixture answer" in o for o in outputs))

    def test_default_dry_run_never_calls_model_or_provider(self):
        with patch.object(w, "_get_json", side_effect=AssertionError("NETWORK PROHIBITED")), \
             patch.object(w, "run_wave", side_effect=AssertionError("MODEL PROHIBITED")):
            self.assertEqual(w.main(["missions/sample.json"]), 0)

    def test_no_external_host_credentials_redirect_or_malformed_urls(self):
        bad = [
            "https://127.0.0.1:11434/v1",
            "http://localhost.evil.com:11434/v1",
            "http://192.168.1.8:11434/v1",
            "http://user:password@127.0.0.1:11434/v1",
            "http://127.0.0.1:11434/v1?x=1",
            "http://127.0.0.1:11434/v1/../../secrets",
            "http://127.0.0.1:11434/v2",
            "file:///etc/passwd",
        ]
        for bad_url in bad:
            obj = {**self.provider, "endpoint": bad_url}
            with self.subTest(url=bad_url), self.assertRaises(w.Unavailable):
                w.validate_backend(obj)
        with self.assertRaises(w.Unavailable):
            w.NoRedirect().redirect_request(None, None, 307, "move", {},
                                             "https://evil.example/secret")

    def test_uninstalled_model_fails_before_any_inference(self):
        config = {**self.provider, "model": "not-installed:20b"}
        with self.assertRaisesRegex(w.Unavailable, "NOT_INSTALLED"):
            w.run_wave(mission.read_small_json(ROOT / "missions/sample.json"),
                       self.repos, config)
        self.assertEqual(FakeModels.requests, [])

    def test_bad_worker_or_role_denied(self):
        for worker, role in [("worker-100", "code-reviewer"),
                             ("../../escape", "code-reviewer"),
                             ("worker-01", "admin-root")]:
            with self.subTest(worker=worker, role=role), self.assertRaises(w.Unavailable):
                w.infer(self.provider, self.provider["model"], role, worker,
                        "title", "description", "mehmetcerdik457-ctrl/Gpt-asistan")

    def test_nonexistent_server_fails_closed_not_fake_pass(self):
        bad = {**self.provider, "endpoint": "http://127.0.0.1:1/v1"}
        with self.assertRaisesRegex(w.Unavailable, "UNAVAILABLE"):
            w.probe(bad)


if __name__ == "__main__":
    unittest.main()
