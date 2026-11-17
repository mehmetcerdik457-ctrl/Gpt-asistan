"""Offline tests for the TinyFish setup diagnostics."""
import json
import unittest

from scripts.tinyfish_preflight import _major, inspect_environment


class TinyFishPreflightTests(unittest.TestCase):
    def test_node_version_parser(self):
        self.assertEqual(_major("v24.1.0"), 24)
        self.assertEqual(_major("20.19.0"), 20)
        self.assertIsNone(_major(None))
        self.assertIsNone(_major("unknown"))

    def test_preflight_never_displays_api_key_value(self):
        secret = "never-print-this-test-secret"
        report = inspect_environment(
            {"TINYFISH_API_KEY": secret},
            which=lambda _name: None,
        )
        serialized = json.dumps(report)
        self.assertTrue(report["tinyfish_api_key_present"])
        self.assertFalse(report["api_key_value_exposed"])
        self.assertNotIn(secret, serialized)
        self.assertEqual(report["network_requests_made"], 0)
        self.assertEqual(report["browser_runs_started"], 0)
        self.assertEqual(report["paid_operations_started"], 0)

    def test_missing_key_is_reported_without_failure(self):
        report = inspect_environment({}, which=lambda _name: None)
        self.assertFalse(report["tinyfish_api_key_present"])
        self.assertEqual(report["mode"], "OFFLINE_PREFLIGHT")


if __name__ == "__main__":
    unittest.main()
