import sqlite3

from kral.safe import assistant


def test_init_db_is_idempotent_and_save_list_roundtrip(tmp_path, monkeypatch):
    database = tmp_path / "mem.db"
    monkeypatch.setenv("KRAL_DB_PATH", str(database))

    assistant.init_db()
    assistant.init_db()

    assert assistant.save("hello")
    assert len(assistant.list_last()) == 1
    assert assistant.list_last()[0][1] == "hello"

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM mem").fetchone()[0] == 1


def test_save_rejects_empty_whitespace_and_overlong_text(tmp_path, monkeypatch):
    monkeypatch.setenv("KRAL_DB_PATH", str(tmp_path / "mem.db"))
    assistant.init_db()

    assert assistant.save("") is False
    assert assistant.save(" \t\n ") is False
    assert assistant.save("x" * 4097) is False
    assert assistant.list_last() == []


def test_speak_returns_false_when_termux_command_is_missing(monkeypatch):
    def missing_command(*args, **kwargs):
        raise FileNotFoundError("not installed")

    monkeypatch.setattr(assistant.subprocess, "run", missing_command)

    assert assistant.speak("hello") is False


def test_speak_returns_false_and_logs_nonzero_or_timeout(monkeypatch, caplog):
    class FailedProcess:
        returncode = 1

    monkeypatch.setattr(assistant.subprocess, "run", lambda *args, **kwargs: FailedProcess())
    assert assistant.speak("hello") is False
    assert "status 1" in caplog.text

    def timeout(*args, **kwargs):
        raise assistant.subprocess.TimeoutExpired("termux-tts-speak", 30)

    monkeypatch.setattr(assistant.subprocess, "run", timeout)
    assert assistant.speak("hello") is False
    assert "timed out" in caplog.text


def test_main_handles_keyboard_interrupt(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("KRAL_DB_PATH", str(tmp_path / "mem.db"))
    monkeypatch.setenv("KRAL_LOG_DIR", str(tmp_path / "logs"))

    def interrupted_input(_prompt):
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", interrupted_input)
    assistant.main()

    assert "Kral Asistan" in capsys.readouterr().out
