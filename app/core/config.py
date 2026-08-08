from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Application settings, read from environment variables and `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "ai-agent-fastapi"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "dev"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = ["*"]

    # Database. The driver must be spelled out: a plain `postgresql://` URL
    # loads psycopg and fails, since the engine here is async.
    DATABASE_URL: str = ""
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_PRE_PING: bool = True
    # Seconds to wait for a connection. Without this a request hangs on the
    # OS-level TCP timeout whenever the database is unreachable.
    DB_CONNECT_TIMEOUT: float = 5.0
    # Set to run the database tests; they are skipped when this is unset.
    TEST_DATABASE_URL: str | None = None

    # Logging. Console only; nothing is written to disk.
    LOG_LEVEL: str = "INFO"
    # uvicorn's own access log duplicates RequestLoggingMiddleware, which also
    # records a request id and duration. Off by default; turn on to compare.
    LOG_UVICORN_ACCESS: bool = False

    # RAG. Credentials and deployment-specific names only - chunking sizes,
    # upload limits and vector widths are constants in the modules that use
    # them, not configuration.
    # Never give credentials a default: this file is committed, `.env` is not.
    OPENAI_API_KEY: str | None = None
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_CHAT_MODEL: str = "gpt-4o-mini"
    QDRANT_URL: str | None = None
    QDRANT_API_KEY: str | None = None
    QDRANT_COLLECTION: str = "document_chunks"

@lru_cache
def get_settings() -> Settings:
    """Cached settings, usable as a FastAPI dependency."""
    return Settings()

settings = get_settings()