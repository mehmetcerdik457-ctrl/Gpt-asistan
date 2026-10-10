import io
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core import LLMClient, LLMError, Registry, load_config


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class CoreTests(unittest.TestCase):
    def test_default_is_local(self):
        c = load_config(env={})
        self.assertEqual(c.provider, "local")
        self.assertIn("11434", c.base_url)

    def test_env_selects_openai(self):
        c = load_config(env={"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "x"})
        self.assertEqual(c.provider, "openai")
        self.assertTrue(c.base_url.startswith("https://api.openai.com"))

    def test_bad_provider(self):
        with self.assertRaises(ValueError):
            load_config(env={"LLM_PROVIDER": "nope"})

    def test_openai_requires_key(self):
        with self.assertRaises(LLMError):
            LLMClient(load_config(env={"LLM_PROVIDER": "openai"})).chat([])

    def test_chat(self):
        seen = {}

        def opener(req, timeout=None):
            seen["url"] = req.full_url
            return FakeResp(json.dumps({"choices": [{"message": {"content": "hi"}}]}).encode())

        out = LLMClient(load_config(env={}), opener=opener).chat([{"role": "user", "content": "yo"}])
        self.assertEqual(out, "hi")
        self.assertTrue(seen["url"].endswith("/chat/completions"))

    def test_registry(self):
        r = Registry()

        @r.tool()
        def add(a, b):
            return a + b

        self.assertEqual(r.call_tool("add", 1, 2), 3)
        self.assertEqual(r.tools(), ["add"])
        with self.assertRaises(ValueError):
            r.register_tool("add", add)
        with self.assertRaises(KeyError):
            r.call_tool("zzz")


if __name__ == "__main__":
    unittest.main()
