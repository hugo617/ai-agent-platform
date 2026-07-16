"""ORM model for chat messages within a conversation."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class Message(Base):
    """A single message (user or assistant) inside a conversation."""

    __tablename__ = "messages"
    __table_args__ = (
        # Composite (tenant_id, created_at) backs the dashboard trends GROUP BY
        # date scan: turns the store-level "WHERE tenant_id=? AND created_at>=?"
        # into an index range scan. Name mirrors the alembic migration
        # (add_trend_indexes) so ``alembic check`` sees model/DB in sync.
        Index(
            "ix_messages_tenant_created_at",
            "tenant_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    tenant_id: Mapped[str] = mapped_column(String(32), index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Token usage for assistant messages (NULL for user messages and for
    # assistant messages persisted before this column existed). Populated by
    # the chat endpoint from ``stream_agent``'s usage payload. ``model`` is
    # the model that *actually served* the request (resolved tenant > platform
    # > env), not necessarily ``Agent.model``.
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Outcome of an assistant turn. "completed" is the normal case; "failed"
    # marks a turn that errored (LLM/provider failure) — the chat endpoint
    # persists such a row so the failure is auditable and the UI can surface a
    # retry affordance instead of a silent SSE drop. ``error`` carries the
    # exception text for failed turns (NULL otherwise).
    status: Mapped[str] = mapped_column(
        String(20), default="completed", server_default="completed"
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Message {self.id} role={self.role}>"
