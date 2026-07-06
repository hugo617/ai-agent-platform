"""Application settings — loaded from environment variables / .env file."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="ignore"
    )

    # Application
    app_name: str = "ai-agent-platform"
    app_env: str = "development"
    app_debug: bool = True
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:3000"]

    # Database
    database_url: str = "sqlite+aiosqlite:///:memory:"

    # Logto (auth)
    logto_endpoint: str = "http://localhost:3001"
    logto_issuer: str = "http://localhost:3001/oidc"
    logto_audience: str = "http://localhost:8000/api"
    logto_admin_subject: str = "admin-user"

    # pycasbin
    casbin_model_path: str = "casbin_model.conf"

    # LLM
    openai_api_key: str = "sk-replace-me"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @property
    def is_testing(self) -> bool:
        return self.app_env == "testing"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
