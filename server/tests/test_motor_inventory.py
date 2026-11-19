import unittest

from server.motor_inventory import inventory


class MotorInventoryTests(unittest.TestCase):
    def test_catalog_covers_engine_and_bridge_categories(self):
        rows = inventory({})
        ids = {row["id"] for row in rows}
        self.assertTrue({
            "openai-responses", "android-compatible-endpoint", "owner-gateway",
            "omega-openai", "openai-agents-sdk", "legacy-cihat-apk",
            "rish-mcp", "google-gemini-vertex", "local-ollama", "ztn-gpt",
        }.issubset(ids))
        self.assertIn("local-model-runtime", {row["kind"] for row in rows})
        self.assertIn("device-tool-bridge", {row["kind"] for row in rows})

    def test_missing_provider_config_is_not_live_access(self):
        rows = {row["id"]: row for row in inventory({})}
        self.assertFalse(rows["openai-responses"]["configuration_present"])
        self.assertFalse(rows["openai-responses"]["model_allowlist_present"])
        self.assertFalse(rows["owner-gateway"]["configuration_present"])
        self.assertTrue(all(not row["live_tested"] for row in rows.values()))

    def test_config_presence_only_reports_booleans_and_never_values(self):
        env = {
            "OPENAI_API_KEY": "do-not-return-this-secret",
            "OPENAI_ALLOWED_MODELS": "test-model",
            "KRAL_OWNER_GATEWAY_URL": "https://models.example.test/v1/chat/completions",
            "KRAL_OWNER_GATEWAY_HOST": "models.example.test",
            "KRAL_OWNER_GATEWAY_TOKEN": "do-not-return-this-token",
            "KRAL_OWNER_GATEWAY_MODEL": "test-model",
        }
        rows = inventory(env)
        rendered = repr(rows)
        self.assertNotIn("do-not-return-this-secret", rendered)
        self.assertNotIn("do-not-return-this-token", rendered)
        indexed = {row["id"]: row for row in rows}
        self.assertTrue(indexed["openai-responses"]["configuration_present"])
        self.assertTrue(indexed["openai-responses"]["model_allowlist_present"])
        self.assertTrue(indexed["owner-gateway"]["configuration_present"])
        self.assertFalse(indexed["owner-gateway"]["live_tested"])

    def test_partial_gateway_configuration_is_not_configured(self):
        rows = {row["id"]: row for row in inventory({
            "KRAL_OWNER_GATEWAY_URL": "https://models.example.test/v1/chat/completions",
            "KRAL_OWNER_GATEWAY_HOST": "models.example.test",
            "KRAL_OWNER_GATEWAY_MODEL": "test-model",
        })}
        self.assertFalse(rows["owner-gateway"]["configuration_present"])


if __name__ == "__main__":
    unittest.main()
