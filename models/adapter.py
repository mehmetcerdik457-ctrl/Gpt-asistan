import json
from abc import ABC, abstractmethod
from urllib.error import URLError
from urllib.request import Request, urlopen


class BaseModel(ABC):
    @abstractmethod
    def generate(self, prompt):
        """Generate a response for a prompt."""

    @abstractmethod
    def status(self):
        """Return a non-sensitive description of this adapter."""


class NullModel(BaseModel):
    def generate(self, prompt):
        return None

    def status(self):
        return "offline stub"


class OpenAIModel(BaseModel):
    endpoint = "https://api.openai.com/v1/chat/completions"

    def __init__(self, config):
        if config.enable_offline_mode or not config.openai_api_key:
            raise ValueError("OpenAI requires offline mode disabled and an API key.")
        self._api_key = config.openai_api_key

    def generate(self, prompt):
        body = json.dumps(
            {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
            }
        ).encode("utf-8")
        request = Request(
            self.endpoint,
            data=body,
            headers={
                "Authorization": "Bearer " + self._api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
        except URLError as exc:
            raise RuntimeError("OpenAI request failed.") from exc
        return result["choices"][0]["message"]["content"]

    def status(self):
        return "OpenAI API"


class LocalModel(BaseModel):
    def generate(self, prompt):
        raise NotImplementedError("Local model inference is not integrated.")

    def status(self):
        return "not integrated"
