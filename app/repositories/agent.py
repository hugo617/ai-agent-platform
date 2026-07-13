"""Agent repository (tenant-scoped)."""

from sqlalchemy import func, select

from app.models.agent import Agent
from app.repositories.base import TenantScopedRepository


class AgentRepository(TenantScopedRepository[Agent]):
    model = Agent

    async def count_for_tenant(self, tenant_id: str) -> int:
        """Count agents in a tenant (used by the dashboard stat card)."""
        stmt = (
            select(func.count())
            .select_from(Agent)
            .where(Agent.tenant_id == tenant_id)
        )
        return int((await self.db.execute(stmt)).scalar_one())

    async def count_all(self) -> int:
        """Count agents across every tenant (super_admin overview)."""
        stmt = select(func.count()).select_from(Agent)
        return int((await self.db.execute(stmt)).scalar_one())
