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

    # LLM — defaults target DeepSeek (OpenAI-compatible endpoint). The fields
    # are named ``openai_*`` because the code talks to them via langchain's
    # ``ChatOpenAI`` class, which any OpenAI-compatible API (DeepSeek, etc.)
    # works with unchanged. These are the last-resort fallback when neither a
    # tenant-level nor platform-level LLM config row exists in the DB.
    openai_api_key: str = "sk-replace-me"
    openai_base_url: str = "https://api.deepseek.com"
    openai_model: str = "deepseek-chat"

    # Field-level encryption — Fernet key (base64 urlsafe 32 bytes) used to
    # encrypt secrets stored in the DB (e.g. LLM API keys). Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # The default is a throwaway key shared here only so dev/test work out of
    # the box; non-dev environments must override it (enforced below).
    field_encryption_key: str = (
        "UxCQS2ohSvdIRjZfiNyCi5uWoy8FLLiIXonkf28M4r8="  # dev/test only
    )

    # Periodic-job scheduler (priority 54). Defaults to False so the test
    # suite — which calls create_app() once per test — never spins up real
    # cron jobs that would outlive the test. Production deployments set this
    # to True (on exactly one replica; multi-replica would double-fire crons).
    scheduler_enabled: bool = False

    @model_validator(mode="after")
    def _secrets_not_default(self) -> "Settings":
        """Reject placeholder secrets outside development/testing.

        A production deploy that forgets to set JWT_SECRET or
        FIELD_ENCRYPTION_KEY would otherwise sign local tokens with a
        publicly-known key or encrypt DB secrets with a shared one. Runs as a
        model_validator (after all fields are populated) so it sees ``app_env``
        loaded from the .env file, not just the raw shell env.
        """
        if self.app_env in ("development", "testing"):
            return self
        if self.jwt_secret == "change-me-in-production":
            raise ValueError(
                "JWT_SECRET must be changed from its default in non-dev environments"
            )
        if self.field_encryption_key.startswith("UxCQS2ohSvdIRjZfiNyC"):
            raise ValueError(
                "FIELD_ENCRYPTION_KEY must be generated for this deployment"
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
