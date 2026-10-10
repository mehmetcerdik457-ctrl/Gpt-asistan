import os
from pathlib import Path


class Config:
    def __init__(self):
        try:
            from dotenv import load_dotenv
        except ImportError:
            pass
        else:
            load_dotenv(override=False)

        self.db_path = Path(
            os.environ.get(
                "KRAL_DB_PATH",
                Path(__file__).resolve().parent.parent / "kral" / "safe" / "mem.db",
            )
        ).expanduser()
        self.log_dir = Path(
            os.environ.get(
                "KRAL_LOG_DIR",
                Path(__file__).resolve().parent.parent / "kral" / "safe",
            )
        ).expanduser()
        self.openai_api_key = os.environ.get("OPENAI_API_KEY", "")
        self.enable_offline_mode = _env_bool("ENABLE_OFFLINE_MODE", True)
        self.enable_local_models = _env_bool("ENABLE_LOCAL_MODELS", True)
        self.log_level = os.environ.get("KRAL_LOG_LEVEL", "INFO").upper()

    def to_dict(self):
        return {
            "db_path": str(self.db_path),
            "log_dir": str(self.log_dir),
            "openai_configured": bool(self.openai_api_key),
            "enable_offline_mode": self.enable_offline_mode,
            "enable_local_models": self.enable_local_models,
            "log_level": self.log_level,
        }


def _env_bool(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
