"""Application settings — loaded from environment variables / .env file."""

import json
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve the .env path relative to the project root (two levels up from this
# file: app/core/config.py → app/core → app → project root). Using an absolute
# path is necessary because pydantic-settings resolves relative env_file paths
# against the process cwd, which differs between `uvicorn`, `alembic`, `pytest`.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE), env_file_encoding="utf-8", extra="ignore"
    )

    # Application
    app_name: str = "ai-agent-platform"
    app_env: str = "development"
    app_debug: bool = True
    api_v1_prefix: str = "/api/v1"
    # Stored as a raw string (JSON array or comma-separated) so pydantic-settings
    # never tries to JSON-parse a bare URL. Use ``settings.cors_origins_list``.
    cors_origins: str = "http://localhost:3000"

    # Database — required in production; tests inject it via the environment.
    database_url: str

    # Logto (auth) — verifies externally issued JWT (OIDC).
    logto_endpoint: str = "http://localhost:3001"
    logto_issuer: str = "http://localhost:3001/oidc"
    logto_audience: str = "http://localhost:8000/api"
    logto_admin_subject: str = "admin-user"

    # Local password auth (bcrypt) — mints HS256 JWTs with iss="local"
    # that flow through the same get_current_user pipeline as Logto tokens.
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    salt_rounds: int = 12
    access_token_ttl_minutes: int = 60
    session_ttl_hours: int = 168  # 7 days

    # Frontend URL — used for welcome/reset emails and CORS default.
    app_url: str = "http://localhost:3000"

    # pycasbin
    casbin_model_path: str = "casbin_model.conf"

    # LLM
    openai_api_key: str = "sk-replace-me"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _coerce_cors(cls, v):
        """Normalise to a plain string (JSON array or comma-separated)."""
        if isinstance(v, list):
            return ",".join(v)
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse ``cors_origins`` into a list (JSON array or comma-separated)."""
        v = self.cors_origins.strip()
        if v.startswith("["):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                pass
        return [o.strip() for o in v.split(",") if o.strip()]

    @property
    def is_testing(self) -> bool:
        return self.app_env == "testing"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
