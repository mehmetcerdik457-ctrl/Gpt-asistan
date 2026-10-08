"""Offline owner API contract tests; mocked model, no paid inference."""
import http.client
import json
import threading
import unittest

import server


TOKEN = "A" * 48


class OwnerApiTests(unittest.TestCase):
    def setUp(self):
        self.seen = []
        self.srv = server.make_server(
            port=0, token=TOKEN,
            answer=lambda prompt: (self.seen.append(prompt) or "ok", "fixture", "fixture-model")
        )
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.thread.join(timeout=3)

    def call(self, method, path, body=None, auth=None, content_type="application/json", **headers):
        connection = http.client.HTTPConnection("127.0.0.1", self.srv.server_port, timeout=3)
        h = {"Content-Type": content_type}
        if auth is not None:
            h["Authorization"] = auth
        h.update(headers)
        connection.request(method, path, body=body, headers=h)
        response = connection.getresponse()
        payload = json.loads(response.read())
        result = response.status, payload, dict(response.getheaders())
        connection.close()
        return result

    def test_authenticated_request_and_no_store(self):
        status, value, headers = self.call(
            "POST", "/v1/ask", json.dumps({"prompt": "Merhaba"}), "Bearer " + TOKEN
        )
        self.assertEqual(status, 200)
        self.assertEqual(value["answer"], "ok")
        self.assertEqual(value["provider"], "fixture")
        self.assertEqual(self.seen, ["Merhaba"])
        self.assertEqual(headers.get("Cache-Control"), "no-store")

    def test_unauthorized_never_calls_model(self):
        for auth in (None, "Bearer wrong", "Basic " + TOKEN):
            status, _, _ = self.call("POST", "/v1/ask", '{"prompt":"x"}', auth)
            self.assertEqual(status, 401)
        self.assertEqual(self.seen, [])

    def test_invalid_requests_fail_before_model(self):
        auth = "Bearer " + TOKEN
        samples = [
            ('not-json', "application/json", 400),
            ('[]', "application/json", 400),
            ('{"prompt":""}', "application/json", 400),
            ('{"prompt":4}', "application/json", 400),
            ('{"prompt":"test","extra":1}', "application/json", 400),
            ('{"prompt":"ok"}', "text/plain", 415),
            ('X' * (server.MAX_REQUEST_BYTES + 1), "application/json", 413),
        ]
        for body, content_type, expected in samples:
            with self.subTest(body=body[:35]):
                status, _, _ = self.call("POST", "/v1/ask", body, auth, content_type)
                self.assertEqual(status, expected)
        self.assertEqual(self.seen, [])

    def test_health_and_unknown_path(self):
        self.assertEqual(self.call("GET", "/health")[0], 200)
        self.assertEqual(self.call("GET", "/missing")[0], 404)

    def test_provider_failure_is_sanitized(self):
        self.srv.answer = lambda prompt: (_ for _ in ()).throw(RuntimeError("secret-key"))
        status, response, _ = self.call("POST", "/v1/ask", '{"prompt":"x"}', "Bearer " + TOKEN)
        self.assertEqual(status, 503)
        self.assertNotIn("secret-key", json.dumps(response))

    def test_capacity_limit(self):
        for _ in range(4):
            self.assertTrue(self.srv.capacity.acquire(blocking=False))
        try:
            self.assertEqual(self.call("POST", "/v1/ask", '{"prompt":"x"}', "Bearer " + TOKEN)[0], 429)
        finally:
            for _ in range(4):
                self.srv.capacity.release()

    def test_server_configuration_is_fail_closed(self):
        with self.assertRaises(ValueError):
            server.make_server(token="weak")
        with self.assertRaises(ValueError):
            server.make_server(host="0.0.0.0", port=0, token=TOKEN)
        with self.assertRaises(ValueError):
            server.make_server(port=-1, token=TOKEN)


if __name__ == "__main__":
    unittest.main()
