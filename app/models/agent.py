"""ORM models for AI agents."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
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

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("agents.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Conversation {self.id} agent={self.agent_id}>"
