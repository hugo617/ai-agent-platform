"""ORM models for AI agents."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class Agent(Base):
    """A user-defined AI agent within a tenant."""

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String(64), default="deepseek-chat")
    # Inference parameters — let each agent tune LLM behaviour (creative vs
    # deterministic). ``temperature`` always has a value (default 0.7, a more
    # general default than the previous hardcoded 0.3); ``max_tokens``/``top_p``
    # are nullable so "not set" means "use the provider default" (we simply
    # don't forward them to ChatOpenAI).
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    temperature: Mapped[float] = mapped_column(
        Float, default=0.7, server_default="0.7"
    )
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    top_p: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Agent {self.id} {self.name} tenant={self.tenant_id}>"


class Conversation(Base):
    """A chat conversation with an agent."""

    __tablename__ = "conversations"
    __table_args__ = (
        # Composite (tenant_id, created_at) backs the dashboard trends GROUP BY
        # date scan: turns the store-level "WHERE tenant_id=? AND created_at>=?"
        # into an index range scan. Name mirrors the alembic migration
        # (add_trend_indexes) so ``alembic check`` sees model/DB in sync.
        Index(
            "ix_conversations_tenant_created_at",
            "tenant_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("agents.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    # Optional customer attribution (Token 费用管理系列 3/4). Nullable: not
    # every conversation is tied to a customer (staff internal queries). SET
    # NULL on hard-delete so historical conversations survive; soft-delete
    # (CustomerProfile.is_deleted) keeps the value for traceability.
    customer_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Conversation {self.id} agent={self.agent_id}>"
