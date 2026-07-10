"""ORM model for tenant/platform-level LLM configuration.

A row stores everything needed to call an OpenAI-compatible LLM: the API key
(encrypted), base_url, default model, and the selectable model list. Two
scopes share one table:

  - **platform level**: ``tenant_id IS NULL`` — set by super admins, the
    fallback for any tenant without its own row.
  - **tenant level**: ``tenant_id = <id>`` — overrides the platform row.

Uniqueness is enforced by the service-layer upsert (one active row per scope),
not by a DB constraint — a partial unique index on ``tenant_id`` would need
``NULLS NOT DISTINCT`` semantics that differ between Postgres and SQLite, which
clashes with the project's dual-DB rule (see AGENTS.md).
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class LlmConfig(Base):
    """An LLM provider configuration, scoped to platform or tenant level."""

    __tablename__ = "llm_configs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    # NULL = platform-wide (super admin); non-null = tenant override.
    tenant_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    # Plaintext mask echoed by GET (e.g. "sk-***wxyz"); never the real key.
    api_key_hint: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    base_url: Mapped[str] = mapped_column(String(255), nullable=False)
    default_model: Mapped[str] = mapped_column(String(64), nullable=False)
    # JSONB on Postgres, plain JSON on SQLite (tests). server_default must match
    # the migration so ``alembic check`` sees no drift.
    available_models: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"),
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        scope = self.tenant_id or "platform"
        return f"<LlmConfig {self.id} scope={scope} model={self.default_model}>"
