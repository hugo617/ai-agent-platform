"""Repository for the agent_specialists association table (priority 58).

Stateless join ops: attach/detach a specialist to/from an orchestrator. The
caller (AgentService) validates tenant scoping + business rules (no
self-attach, specialist can't itself be an orchestrator, etc.) before calling
these — the repository is a thin data-access layer that trusts its caller.
"""

from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.agent_specialist import AgentSpecialist
from app.repositories.base import BaseRepository


class AgentSpecialistRepository(BaseRepository[AgentSpecialist]):
    """Join-table ops: attach/detach a specialist to/from an orchestrator."""

    model = AgentSpecialist

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def list_for_orchestrator(self, orchestrator_id: str) -> list[AgentSpecialist]:
        """All specialist memberships for one orchestrator (any tenant).

        The caller is responsible for tenant scoping — this returns the raw
        join rows so the service can decide how to filter/aggregate.
        """
        stmt = select(AgentSpecialist).where(
            AgentSpecialist.orchestrator_id == orchestrator_id
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_specialist_agents(
        self, orchestrator_id: str, tenant_id: str
    ) -> list[Agent]:
        """The specialist Agent rows attached to an orchestrator.

        JOIN ``agents`` to resolve each specialist_id to its full row, and
        enforce that every specialist actually belongs to the same tenant as
        the orchestrator — defense-in-depth against any cross-tenant leak even
        if a membership row were somehow created out-of-band.
        """
        stmt = (
            select(Agent)
            .join(
                AgentSpecialist, AgentSpecialist.specialist_id == Agent.id
            )
            .where(
                AgentSpecialist.orchestrator_id == orchestrator_id,
                Agent.tenant_id == tenant_id,
            )
            .order_by(AgentSpecialist.created_at.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def exists(self, orchestrator_id: str, specialist_id: str) -> bool:
        stmt = select(
            exists().where(
                AgentSpecialist.orchestrator_id == orchestrator_id,
                AgentSpecialist.specialist_id == specialist_id,
            )
        )
        result = await self.db.execute(stmt)
        return bool(result.scalar())

    async def attach(
        self, orchestrator_id: str, specialist_id: str
    ) -> AgentSpecialist:
        link = AgentSpecialist(
            orchestrator_id=orchestrator_id, specialist_id=specialist_id
        )
        self.db.add(link)
        await self.db.flush()
        return link

    async def detach(self, orchestrator_id: str, specialist_id: str) -> bool:
        """Delete the link row; return whether a row was actually removed."""
        stmt = delete(AgentSpecialist).where(
            AgentSpecialist.orchestrator_id == orchestrator_id,
            AgentSpecialist.specialist_id == specialist_id,
        )
        result = await self.db.execute(stmt)
        return (result.rowcount or 0) > 0
