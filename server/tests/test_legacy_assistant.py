import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from kral.safe import assistant


class LegacyAssistantVoiceTests(unittest.TestCase):
    def test_speak_reports_success_only_when_termux_returns_zero(self):
        with patch.object(assistant.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run:
            self.assertTrue(assistant.speak("  Merhaba  "))
        run.assert_called_once_with(["termux-tts-speak", "Merhaba"], check=False)

    def test_speak_reports_nonzero_exit_as_failure(self):
        with patch.object(assistant.subprocess, "run", return_value=SimpleNamespace(returncode=1)):
            self.assertFalse(assistant.speak("Merhaba"))

    def test_speak_reports_missing_engine_as_failure(self):
        with patch.object(assistant.subprocess, "run", side_effect=FileNotFoundError):
            self.assertFalse(assistant.speak("Merhaba"))

    def test_speak_does_not_invoke_engine_for_empty_text(self):
        with patch.object(assistant.subprocess, "run") as run:
            self.assertFalse(assistant.speak("  \t"))
        run.assert_not_called()

    def test_cli_never_claims_speech_succeeded_when_engine_is_missing(self):
        original_db = assistant.DB
        with tempfile.TemporaryDirectory() as temp_dir:
            assistant.DB = str(Path(temp_dir) / "assistant.db")
            output = io.StringIO()
            try:
                with patch("builtins.input", side_effect=["/soyle merhaba", "/cik"]), \
                     patch.object(assistant.subprocess, "run", side_effect=FileNotFoundError), \
                     contextlib.redirect_stdout(output):
                    assistant.main()
            finally:
                assistant.DB = original_db
        self.assertIn("Sesli yanıt başarısız", output.getvalue())
        self.assertNotIn("Sesli yanıt tamamlandı", output.getvalue())


if __name__ == "__main__":
    unittest.main()
