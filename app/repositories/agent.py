"""Agent repository (tenant-scoped)."""

from sqlalchemy import func, select

from app.models.agent import Agent
from app.repositories.base import TenantScopedRepository


class AgentRepository(TenantScopedRepository[Agent]):
    """Agent data access, tenant-scoped.

    All reads filter ``is_deleted=False`` — Agent uses soft delete (mirrors
    Customer/Role/Document/Wallet) so deleting an Agent keeps its history
    (Conversations, UsageEvents) joinable instead of CASCADE-destroying it.
    """

    model = Agent

    async def get_for_tenant(self, obj_id: str, tenant_id: str) -> Agent | None:
        """A live (non-deleted) agent by id within a tenant."""
        stmt = select(Agent).where(
            Agent.id == obj_id,
            Agent.tenant_id == tenant_id,
            Agent.is_deleted.is_(False),
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list_for_tenant(
        self, tenant_id: str, limit: int = 100, offset: int = 0
    ) -> list[Agent]:
        """All live agents in a tenant, newest first."""
        stmt = (
            select(Agent)
            .where(
                Agent.tenant_id == tenant_id,
                Agent.is_deleted.is_(False),
            )
            .order_by(Agent.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def count_for_tenant(self, tenant_id: str) -> int:
        """Count live agents in a tenant (used by the dashboard stat card)."""
        stmt = (
            select(func.count())
            .select_from(Agent)
            .where(
                Agent.tenant_id == tenant_id,
                Agent.is_deleted.is_(False),
            )
        )
        return int((await self.db.execute(stmt)).scalar_one())

    async def count_all(self) -> int:
        """Count live agents across every tenant (super_admin overview)."""
        stmt = select(func.count()).select_from(Agent).where(
            Agent.is_deleted.is_(False)
        )
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
            .where(
                Agent.name.ilike(like),
                Agent.is_deleted.is_(False),
            )
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
                Agent.is_deleted.is_(False),
            )
            .order_by(Agent.created_at.desc())
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def list_for_tenant_by_role(
        self, *, tenant_id: str, is_orchestrator: bool
    ) -> list[Agent]:
        """Agents in a tenant filtered by ``is_orchestrator`` flag.

        Used by the agents-page UI to populate the specialist picker
        (``is_orchestrator=False`` candidates) and to mark orchestrators.
        Ordering matches ``list_for_tenant`` (created_at desc) for a stable
        display order across the two views.
        """
        stmt = (
            select(Agent)
            .where(
                Agent.tenant_id == tenant_id,
                Agent.is_orchestrator.is_(is_orchestrator),
                Agent.is_deleted.is_(False),
            )
            .order_by(Agent.created_at.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())
