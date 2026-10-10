"""Configuration loader: defaults < JSON file < environment variables.

Secrets are only ever read from the environment, never from files in the repo.
"""
import json
import os
from dataclasses import dataclass

DEFAULTS = {
    "provider": "local",
    "model": "llama3",
    "timeout": 60.0,
    "openai_base_url": "https://api.openai.com/v1",
    "local_base_url": "http://localhost:11434/v1",  # Ollama; llama.cpp server: http://localhost:8080/v1
}


@dataclass
class Config:
    provider: str
    model: str
    base_url: str
    api_key: str
    timeout: float


def load_config(path=None, env=None):
    env = os.environ if env is None else env
    data = dict(DEFAULTS)
    path = path or env.get("ASSISTANT_CONFIG")
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            data.update(json.load(fh))
    data["provider"] = env.get("LLM_PROVIDER", data["provider"]).lower()
    data["model"] = env.get("LLM_MODEL", data["model"])
    if data["provider"] not in ("openai", "local"):
        raise ValueError("LLM_PROVIDER must be 'openai' or 'local'")
    default_url = data["openai_base_url"] if data["provider"] == "openai" else data["local_base_url"]
    return Config(
        provider=data["provider"],
        model=data["model"],
        base_url=env.get("LLM_BASE_URL", default_url).rstrip("/"),
        api_key=env.get("OPENAI_API_KEY", "") if data["provider"] == "openai" else env.get("LOCAL_LLM_API_KEY", ""),
        timeout=float(data["timeout"]),
    )
