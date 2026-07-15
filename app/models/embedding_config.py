"""ORM model for tenant/platform-level embedding configuration.

Mirrors :class:`LlmConfig` but for the embeddings provider used by the RAG
pipeline (priority 57). Kept as a separate table because the embeddings
endpoint differs from the chat LLM: DeepSeek (the default chat provider) does
NOT expose an embeddings API, so embeddings must target a different provider
(OpenAI by default). Two scopes share one table:

  - **platform level**: ``tenant_id IS NULL`` — set by super admins, the
    fallback for any tenant without its own row.
  - **tenant level**: ``tenant_id = <id>`` — overrides the platform row.

Uniqueness is enforced by the service-layer upsert (one active row per scope),
not by a DB constraint — a partial unique index on ``tenant_id`` would need
``NULLS NOT DISTINCT`` semantics that differ between Postgres and SQLite, which
clashes with the project's dual-DB rule (see AGENTS.md). This mirrors the
:class:`LlmConfig` decision.

Unlike :class:`LlmConfig` there is no ``available_models`` list — embeddings
use a single model, and the vector dimension is fixed (1536 for
text-embedding-3-small) and lives as a constant on the effective config, never
in the DB.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class EmbeddingConfig(Base):
    """An embeddings provider configuration, scoped to platform or tenant level."""

    __tablename__ = "embedding_configs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    # NULL = platform-wide (super admin); non-null = tenant override.
    tenant_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    # Plaintext mask echoed by GET (e.g. "sk-***wxyz"); never the real key.
    api_key_hint: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    base_url: Mapped[str] = mapped_column(String(255), nullable=False)
    # Single model (no selectable list — embeddings don't need a dropdown).
    model: Mapped[str] = mapped_column(String(64), nullable=False)
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
        return f"<EmbeddingConfig {self.id} scope={scope} model={self.model}>"
