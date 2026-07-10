"""Application settings — loaded from environment variables / .env file."""

import json
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
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
    app_name: str = "agenthub"
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
    # IMPORTANT: the default is a placeholder only safe for local dev. Setting
    # it to the default outside development/testing is rejected at startup so a
    # misconfigured production deploy cannot mint forgeable tokens silently.
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    salt_rounds: int = 12
    access_token_ttl_minutes: int = 10080  # 7 days
    session_ttl_hours: int = 168  # 7 days

    # Frontend URL — used for welcome/reset emails and CORS default.
    app_url: str = "http://localhost:3000"

    # pycasbin
    casbin_model_path: str = "casbin_model.conf"

    # LLM
    openai_api_key: str = "sk-replace-me"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    @model_validator(mode="after")
    def _jwt_secret_not_default(self) -> "Settings":
        """Reject the placeholder JWT secret outside development/testing.

        A production deploy that forgets to set JWT_SECRET would otherwise sign
        local tokens with a publicly-known key — anyone could forge an admin
        token. Runs as a model_validator (after all fields are populated) so it
        sees ``app_env`` loaded from the .env file, not just the raw shell env.
        """
        if (
            self.jwt_secret == "change-me-in-production"
            and self.app_env not in ("development", "testing")
        ):
            raise ValueError(
                "JWT_SECRET must be changed from its default in non-dev environments"
            )
        return self

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
