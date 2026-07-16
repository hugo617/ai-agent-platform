"""ORM model for the agent_specialists association table (priority 58).

A row links an orchestrator Agent to one of its specialist Agents. The
orchestrator (``is_orchestrator=True``) acts as a supervisor: at chat time it
asks a routing LLM which specialist should handle the user's question, then
hands control to that specialist's ReAct agent. Specialists are plain Agents
(``is_orchestrator=False``) that keep their own system_prompt / tools.

This is a stateless join — attaching/detaching = insert/delete a row — so a
plain ``UniqueConstraint`` suffices (no soft delete, mirroring ``GroupTenant``).
Both FKs reference ``agents.id`` with ``ondelete=CASCADE``: deleting either
Agent cleans up its memberships automatically.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class AgentSpecialist(Base):
    """Many-to-many: which specialists an orchestrator Agent can route to.

    Attaching/detaching a specialist = insert/delete a row here (no soft
    delete — the relation either exists or it doesn't). The
    ``UniqueConstraint`` enforces "a specialist is attached to an orchestrator
    at most once".
    """

    __tablename__ = "agent_specialists"
    __table_args__ = (
        UniqueConstraint(
            "orchestrator_id", "specialist_id", name="uq_agent_specialists"
        ),
        Index("idx_agent_specialists_specialist_id", "specialist_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    orchestrator_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    specialist_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<AgentSpecialist orchestrator={self.orchestrator_id} "
            f"specialist={self.specialist_id}>"
        )
