from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: str = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/incident_aiops"
    sync_database_url: str = "postgresql://postgres:postgres@localhost:5432/incident_aiops"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = Field(min_length=16, default="change-this-development-secret")
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 14
    cors_origins: list[AnyHttpUrl | str] = ["http://localhost:3000"]
    llm_provider: str = "fake"
    llm_api_key: str | None = None
    health_retention_days: int = 14

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
