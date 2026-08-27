from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./caretrace.db")
    app_secret: str = os.getenv("APP_SECRET", "caretrace-local-demo-secret")
    encryption_key: str = os.getenv("ENCRYPTION_KEY", "")
    ai_provider: str = os.getenv("AI_PROVIDER", "fixture")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_chat_model: str = os.getenv("OLLAMA_CHAT_MODEL", "qwen3:4b")
    ollama_embed_model: str = os.getenv("OLLAMA_EMBED_MODEL", "embeddinggemma")
    data_decay_threshold_days: int = int(os.getenv("DATA_DECAY_THRESHOLD_DAYS", "90"))
    recent_context_count: int = int(os.getenv("RECENT_CONTEXT_COUNT", "3"))
    rag_top_k: int = int(os.getenv("RAG_TOP_K", "5"))
    glance_max_items: int = int(os.getenv("GLANCE_MAX_ITEMS", "5"))

    @property
    def fernet_key(self) -> bytes:
        if self.encryption_key:
            return self.encryption_key.encode()
        digest = hashlib.sha256(self.app_secret.encode()).digest()
        return base64.urlsafe_b64encode(digest)


settings = Settings()

