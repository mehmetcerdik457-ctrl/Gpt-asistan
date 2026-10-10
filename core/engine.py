from memory import MemoryStorage
from models import NullModel, OpenAIModel

from .config import Config


class CoreEngine:
    def __init__(self, config=None, storage=None, model=None):
        self.config = config or Config()
        self.storage = storage or MemoryStorage(self.config.db_path)
        if model is not None:
            self.model = model
        elif not self.config.enable_offline_mode and self.config.openai_api_key:
            self.model = OpenAIModel(self.config)
        else:
            self.model = NullModel()

    def remember(self, text):
        return self.storage.store(text)

    def recall(self, query=None, limit=20):
        if query is not None:
            return self.storage.search(query, limit=limit)
        return self.storage.retrieve(limit=limit)

    def get_status(self):
        return {
            "offline_mode": self.config.enable_offline_mode,
            "local_models_enabled": self.config.enable_local_models,
            "openai_configured": bool(self.config.openai_api_key),
            "model": self.model.status(),
        }
