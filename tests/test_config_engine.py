from core import Config, CoreEngine
from models import NullModel


def test_config_reads_environment_at_call_time_and_hides_secrets(monkeypatch, tmp_path):
    monkeypatch.setenv("KRAL_DB_PATH", str(tmp_path / "first.db"))
    first = Config()
    monkeypatch.setenv("KRAL_DB_PATH", str(tmp_path / "second.db"))
    monkeypatch.setenv("OPENAI_API_KEY", "sentinel-secret-value")
    monkeypatch.setenv("ENABLE_OFFLINE_MODE", "false")
    second = Config()

    assert first.db_path == tmp_path / "first.db"
    assert second.db_path == tmp_path / "second.db"
    assert second.enable_offline_mode is False
    assert second.to_dict()["openai_configured"] is True
    assert "sentinel-secret-value" not in repr(second.to_dict())
    assert "openai_api_key" not in second.to_dict()


def test_engine_remembers_and_recalls_offline_without_network(monkeypatch, tmp_path):
    monkeypatch.setenv("KRAL_DB_PATH", str(tmp_path / "mem.db"))
    monkeypatch.setenv("OPENAI_API_KEY", "sentinel-secret-value")
    monkeypatch.setenv("ENABLE_OFFLINE_MODE", "true")

    def fail_if_network(*args, **kwargs):
        raise AssertionError("offline mode must not access the network")

    monkeypatch.setattr("models.adapter.urlopen", fail_if_network)
    engine = CoreEngine()

    assert isinstance(engine.model, NullModel)
    assert engine.remember("offline memory")
    assert engine.recall("offline")[0]["text"] == "offline memory"
    assert engine.get_status()["offline_mode"] is True
