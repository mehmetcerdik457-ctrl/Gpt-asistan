"""Signed local HTTP 200 proof using the existing synthetic provider fixture only."""
import unittest
from test_gateway import GatewayHttpTests


class LocalLoopbackProof(unittest.TestCase):
    def test_owner_chat_returns_http_200_on_localhost(self):
        fixture = GatewayHttpTests(methodName="test_signed_live_probe_contract_and_actual_id")
        fixture.setUp()
        try:
            model = fixture.verify_model()
            status, body = fixture.post("chat", {
                "message": "KRAL local loopback verification",
                "model": model,
                "include_memory": False,
            })
            fixture.assertEqual(status, 200)
            fixture.assertEqual(body["contract"], "OMEGA-OWNER-API-V1")
            fixture.assertEqual(body["text"], fixture.provider.answer)
            fixture.assertEqual(body["model"], model)
        finally:
            fixture.tearDown()


if __name__ == "__main__":
    unittest.main(verbosity=2)
