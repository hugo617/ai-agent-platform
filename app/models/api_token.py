"""ORM model for long-lived API tokens (PAT / future OAuth).

A row binds a machine credential to its *issuer*: the token authenticates as
``created_by_user_id`` within a fixed ``tenant_id``, so it inherits that user's
casbin role/permissions and the tenant-scoped isolation stays intact. The
plaintext token is shown **only once** at issue time; only a Fernet ciphertext
(``token_hash``) and a short display prefix are persisted.

Designed for the AtoA (Agent-to-Agent) surface: external AI agents
(Claude Code / Cursor / Codex / any) present this token as a Bearer credential
and ``get_current_user`` resolves it via the ``ahp_`` prefix bypass — every
existing API automatically becomes agent-accessible with no per-route change.

See ``harness/docs/plan-atoa-api-token-auth.md`` for the design rationale.
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


class ApiToken(Base):
    """A long-lived API token authenticating an external agent as its issuer.

    ``token_type`` distinguishes PATs (this task) from future OAuth client
    credentials (reserved, not implemented). ``scopes`` is reserved for
    fine-grained scope limiting; today every token inherits the issuer's full
    permissions.
    """

    __tablename__ = "api_tokens"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    # Fixed tenant — a token cannot switch tenants (prevents cross-tenant escape).
    tenant_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    # The token authenticates AS this user; casbin queries use it verbatim.
    created_by_user_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("users.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # "pat" today; "oauth_client" reserved for a later task.
    token_type: Mapped[str] = mapped_column(String(16), default="pat", server_default="pat")
    # Fernet ciphertext of the plaintext token. Decrypted only to compare on auth.
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    # Short display prefix used to narrow the auth lookup (e.g. "ahp_wxyz1234").
    token_prefix: Mapped[str] = mapped_column(String(32), index=True)
    # JSONB on Postgres, plain JSON on SQLite (tests). server_default matches the
    # migration so ``alembic check`` sees no drift.
    scopes: Mapped[list] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"),
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # NULL = never expires.
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Soft revoke (user-initiated) vs hard delete row.
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, server_default=text("true")
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default=text("false"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<ApiToken {self.id} name={self.name} prefix={self.token_prefix}>"
