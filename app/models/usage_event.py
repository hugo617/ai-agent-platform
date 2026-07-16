"""ORM model for the usage event ledger (token billing foundation).

Every successful assistant turn appends exactly one ``UsageEvent`` row — an
append-only ledger of "this conversation consumed N tokens on model M". This
is the data foundation for billing (task 2), customer attribution (task 3)
and usage dashboards (task 4).

Fields intentionally left nullable for later tasks:
  - ``customer_id``: filled by task 3 (customer-conversation-link) once a
    conversation can be associated with a customer.
  - ``cost``: filled by task 2 (token-wallet-billing) once a pricing table
    exists; until then we record raw tokens only.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class UsageEvent(Base):
    """Append-only ledger entry for one LLM call's token usage."""

    __tablename__ = "usage_events"
    # Composite index for the two dominant query shapes: "tenant usage over
    # time" (dashboard) and "recent events for a conversation" (drill-down).
    __table_args__ = (
        Index("idx_usage_events_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True,
    )
    message_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("messages.id", ondelete="CASCADE"),
        index=True,
    )
    agent_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Filled by task 3 (customer-conversation-link). Nullable now because not
    # every conversation is tied to a customer (e.g. staff internal queries).
    customer_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # SET NULL on user delete so historical usage stats survive (the user row
    # may go away but the ledger entry must keep its place for tenant totals).
    user_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    model: Mapped[str] = mapped_column(String(64))
    prompt_tokens: Mapped[int] = mapped_column(Integer)
    completion_tokens: Mapped[int] = mapped_column(Integer)
    total_tokens: Mapped[int] = mapped_column(Integer)
    # Filled by task 2 (token-wallet-billing) when charging. Nullable now:
    # this task records raw usage only, cost is derived later from pricing.
    cost: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<UsageEvent {self.id} tenant={self.tenant_id} "
            f"total={self.total_tokens} model={self.model}>"
        )
