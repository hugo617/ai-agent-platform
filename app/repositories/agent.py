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

    async def search(
        self, *, keyword: str, limit: int = 5
    ) -> list[Agent]:
        """Case-insensitive name match across every tenant (HQ aggregator).

        Used by the global search endpoint. The caller (super_admin) already
        cleared the cross-tenant guard, so no ``tenant_id`` filter is applied
        here. Stores never reach this branch (they use ``search_for_tenant``).
        """
        like = f"%{keyword}%"
        stmt = (
            select(Agent)
            .where(Agent.name.ilike(like))
            .order_by(Agent.created_at.desc())
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def search_for_tenant(
        self, *, keyword: str, tenant_id: str, limit: int = 5
    ) -> list[Agent]:
        """Case-insensitive name match scoped to one tenant (store view)."""
        like = f"%{keyword}%"
        stmt = (
            select(Agent)
            .where(
                Agent.tenant_id == tenant_id,
                Agent.name.ilike(like),
            )
            .order_by(Agent.created_at.desc())
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).scalars().all())
