"""OpenAI-compatible chat client (works with OpenAI, Ollama, llama.cpp server)."""
import json
import urllib.request

from .config import Config


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, config: Config, opener=None):
        self.config = config
        self._open = opener or urllib.request.urlopen

    def chat(self, messages, **extra):
        cfg = self.config
        if cfg.provider == "openai" and not cfg.api_key:
            raise LLMError("OPENAI_API_KEY is not set")
        body = json.dumps({"model": cfg.model, "messages": messages, **extra}).encode()
        headers = {"Content-Type": "application/json"}
        if cfg.api_key:
            headers["Authorization"] = "Bearer " + cfg.api_key
        req = urllib.request.Request(cfg.base_url + "/chat/completions", data=body, headers=headers, method="POST")
        try:
            with self._open(req, timeout=cfg.timeout) as resp:
                payload = json.loads(resp.read().decode())
            return payload["choices"][0]["message"]["content"]
        except (OSError, KeyError, IndexError, ValueError) as exc:
            raise LLMError("LLM request failed: %s" % exc) from exc
