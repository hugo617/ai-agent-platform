"""Repository for the usage event ledger (tenant-scoped, append-only).

Read paths support the dashboards/reports built in later tasks; writes go
through ``add`` (inherited) and are triggered by the chat endpoint after a
successful assistant turn.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usage_event import UsageEvent
from app.repositories.base import TenantScopedRepository


class UsageEventRepository(TenantScopedRepository[UsageEvent]):
    model = UsageEvent

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def sum_tokens_for_tenant(
        self, tenant_id: str
    ) -> tuple[int, int, int]:
        """Return (prompt, completion, total) token sums for a tenant.

        Used by the tenant-level usage dashboard. Returns zeros when there
        are no events (COALESCE over the aggregate).
        """
        stmt = select(
            func.coalesce(func.sum(UsageEvent.prompt_tokens), 0),
            func.coalesce(func.sum(UsageEvent.completion_tokens), 0),
            func.coalesce(func.sum(UsageEvent.total_tokens), 0),
        ).where(UsageEvent.tenant_id == tenant_id)
        result = await self.db.execute(stmt)
        row = result.one()
        return int(row[0]), int(row[1]), int(row[2])

    async def list_for_tenant(
        self, tenant_id: str, limit: int = 100, offset: int = 0
    ) -> list[UsageEvent]:
        """Most-recent usage events for a tenant (drill-down view)."""
        stmt = (
            select(UsageEvent)
            .where(UsageEvent.tenant_id == tenant_id)
            .order_by(UsageEvent.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_for_conversation(
        self, conversation_id: str, tenant_id: str
    ) -> list[UsageEvent]:
        """Usage events for one conversation (per-turn token breakdown)."""
        stmt = (
            select(UsageEvent)
            .where(
                UsageEvent.tenant_id == tenant_id,
                UsageEvent.conversation_id == conversation_id,
            )
            .order_by(UsageEvent.created_at)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
