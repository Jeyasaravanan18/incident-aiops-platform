import json
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: str = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/incident_aiops"
    sync_database_url: str = "postgresql://postgres:postgres@localhost:5432/incident_aiops"

    @property
    def async_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        if url.startswith("postgresql://") and not url.startswith("postgresql+asyncpg://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    @property
    def sync_database_url_resolved(self) -> str:
        url = self.sync_database_url
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql://", 1)
        if url.startswith("postgresql+asyncpg://"):
            return url.replace("postgresql+asyncpg://", "postgresql://", 1)
        if self.database_url:
            d_url = self.database_url
            if d_url.startswith("postgres://"):
                return d_url.replace("postgres://", "postgresql://", 1)
            if d_url.startswith("postgresql+asyncpg://"):
                return d_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        return url

    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = Field(min_length=16, default="change-this-development-secret")
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 14
    cors_origins_raw: str = Field(default="http://localhost:3000", alias="cors_origins")

    @property
    def cors_origins(self) -> list[str]:
        val = self.cors_origins_raw
        if val.startswith("[") and val.endswith("]"):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    return [str(i) for i in parsed]
            except Exception:
                pass
        return [i.strip() for i in val.split(",") if i.strip()]

    llm_provider: str = "fake"
    llm_api_key: str | None = None
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.6-flash"
    health_retention_days: int = 14

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
