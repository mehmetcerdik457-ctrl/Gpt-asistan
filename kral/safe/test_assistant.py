# -*- coding: utf-8 -*-
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

MODULE_PATH = Path(__file__).with_name("assistant.py")
SPEC = importlib.util.spec_from_file_location("kral_assistant", MODULE_PATH)
assistant = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(assistant)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class KralAssistantTests(unittest.TestCase):
    def test_extract_output(self):
        data = {"output": [{"content": [{"type": "output_text", "text": "merhaba"}]}]}
        self.assertEqual(assistant.extract_output(data), "merhaba")

    def test_auto_provider_prefers_openai(self):
        env = {
            "KRAL_PROVIDER": "auto",
            "OPENAI_API_KEY": "test-openai",
            "HUGGINGFACE_TOKEN": "test-hf",
        }
        with patch.dict(os.environ, env, clear=True):
            provider, _, _, model = assistant.provider_config()
        self.assertEqual(provider, "openai")
        self.assertEqual(model, assistant.DEFAULT_OPENAI_MODEL)

    def test_auto_provider_falls_back_to_huggingface(self):
        env = {"KRAL_PROVIDER": "auto", "HUGGINGFACE_TOKEN": "test-hf"}
        with patch.dict(os.environ, env, clear=True):
            provider, _, base, model = assistant.provider_config()
        self.assertEqual(provider, "huggingface")
        self.assertEqual(base, "https://router.huggingface.co/v1")
        self.assertEqual(model, assistant.DEFAULT_HF_MODEL)

    def test_no_provider_fails_closed(self):
        with patch.dict(os.environ, {"KRAL_PROVIDER": "auto"}, clear=True):
            with self.assertRaises(RuntimeError):
                assistant.provider_config()

    def test_local_memory_uses_private_data_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"XDG_DATA_HOME": tmp}, clear=True):
                assistant.save_note("test")
                rows = assistant.list_notes()
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0][1], "test")
                self.assertTrue((Path(tmp) / "kral-asistan" / "mem.db").exists())

    def test_openai_request_does_not_need_third_party_sdk(self):
        env = {
            "KRAL_PROVIDER": "openai",
            "OPENAI_API_KEY": "test-openai",
            "OPENAI_MODEL": "gpt-5.6-luna",
            "KRAL_CONTEXT_TURNS": "0",
        }
        payload = {"output": [{"content": [{"type": "output_text", "text": "tamam"}]}]}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {**env, "XDG_DATA_HOME": tmp}, clear=True
        ), patch.object(
            assistant.urllib.request, "urlopen", return_value=FakeResponse(payload)
        ) as mocked:
            answer, provider, model = assistant.ask_model("merhaba")
            request = mocked.call_args.args[0]
            self.assertEqual(answer, "tamam")
            self.assertEqual(provider, "openai")
            self.assertEqual(model, "gpt-5.6-luna")
            self.assertEqual(request.full_url, "https://api.openai.com/v1/responses")
            self.assertTrue(request.get_header("Authorization").startswith("Bearer "))


if __name__ == "__main__":
    unittest.main()
