"""Application configuration loaded from environment variables (validated by Pydantic)."""
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Signal Stack"
    environment: str = "development"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://signal:signal@localhost:5432/signalstack"

    # Optional API key. When set, every /api request must send X-API-Key.
    api_key: str | None = None
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Crawling
    crawler_user_agent: str = "SignalStackBot/1.0 (+https://github.com/ayush001sharma/signal-stack; business-intelligence research bot)"
    request_timeout_seconds: float = 20.0
    per_host_delay_seconds: float = 1.5
    max_retries: int = 2
    max_response_bytes: int = 3_000_000
    http_cache_ttl_seconds: int = 900

    # LLM (optional, free, local)
    llm_provider: str = "ollama"  # "ollama" or "none"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    llm_timeout_seconds: float = 180.0

    # Embeddings: "auto" tries sentence-transformers then falls back to TF-IDF
    embeddings_backend: str = "auto"
    embeddings_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Optional Reddit official API (free OAuth app). robots.txt forbids anonymous crawling.
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None

    # Uploads
    upload_dir: Path = Path("./data/uploads")
    max_upload_mb: int = 10

    # Scheduler
    scheduler_enabled: bool = True
    default_timezone: str = "Asia/Kolkata"

    @field_validator("llm_provider")
    @classmethod
    def _llm(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in {"ollama", "none"}:
            raise ValueError("LLM_PROVIDER must be 'ollama' or 'none'")
        return v

    @field_validator("embeddings_backend")
    @classmethod
    def _emb(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in {"auto", "sentence-transformers", "tfidf"}:
            raise ValueError("EMBEDDINGS_BACKEND must be auto, sentence-transformers or tfidf")
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
