"""Repository for the usage event ledger (tenant-scoped, append-only).

Read paths support the dashboards/reports built in later tasks; writes go
through ``add`` (inherited) and are triggered by the chat endpoint after a
successful assistant turn.
"""

from datetime import datetime
from decimal import Decimal

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

    # ---- customer attribution (Token 费用管理系列 3/4) ----

    async def sum_tokens_for_customer(
        self, customer_id: str, tenant_id: str | None = None
    ) -> tuple[int, int, int, Decimal, int, datetime | None]:
        """Aggregate token usage for a customer.

        Returns ``(prompt, completion, total, cost_sum, conversation_count,
        last_active_at)``. ``tenant_id`` optional: None = global (HQ view,
        all stores); set = store-scoped (only this store's service of the
        customer). Returns zeros / None when the customer has no attributed
        usage (COALESCE over the aggregate).
        """
        wheres = [UsageEvent.customer_id == customer_id]
        if tenant_id is not None:
            wheres.append(UsageEvent.tenant_id == tenant_id)
        stmt = select(
            func.coalesce(func.sum(UsageEvent.prompt_tokens), 0),
            func.coalesce(func.sum(UsageEvent.completion_tokens), 0),
            func.coalesce(func.sum(UsageEvent.total_tokens), 0),
            func.coalesce(func.sum(UsageEvent.cost), 0),
            func.count(func.distinct(UsageEvent.conversation_id)),
            func.max(UsageEvent.created_at),
        ).where(*wheres)
        result = await self.db.execute(stmt)
        row = result.one()
        return (
            int(row[0]),
            int(row[1]),
            int(row[2]),
            row[3],
            int(row[4]),
            row[5],
        )
