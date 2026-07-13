"""Dashboard service — trends + HQ overview.

Two endpoints back the rewritten dashboard:

- ``trends`` — daily conversation + message counts for the last N days. Store
  users are scoped to their tenant; super_admin gets the cross-tenant aggregate.
- ``overview`` — super_admin-only platform totals + per-tenant activity Top N.

Trend queries carry a date window; ``days`` is clamped to a sane upper bound
(90) so the GROUP BY date scan stays cheap (plan §风险). The (tenant_id,
created_at) index added by the companion migration makes the store-level GROUP
BY an index range scan.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.agent import AgentRepository
from app.repositories.conversation import ConversationRepository
from app.repositories.customer import CustomerRepository
from app.repositories.dashboard import DashboardRepository
from app.schemas.dashboard import (
    DashboardOverview,
    DashboardTrends,
    PlatformTotals,
    TenantActivityItem,
    TrendPoint,
)
from app.services.permission_service import permission_service

# Upper bound on the trend window. Keeps the GROUP BY scan bounded; the plan's
# risk table notes "限制 days ≤ 90". Anything larger is clamped to 90.
MAX_TREND_DAYS = 90


def _fill_continuous(
    rows: list[tuple[str, int, int]], days: int, now: datetime
) -> list[TrendPoint]:
    """Fill missing days with zero-valued points so the chart is continuous.

    ``rows`` is ``[(date_iso, convs, msgs), ...]`` ordered oldest → newest from
    the GROUP BY. We expand to a full ``days``-day window ending today, filling
    any day with no row as 0/0. Ordered oldest → newest (left → right on chart).
    """
    today = now.date()
    window_start = today - timedelta(days=days - 1)
    by_date = {d: (c, m) for d, c, m in rows}
    points: list[TrendPoint] = []
    for i in range(days):
        d = window_start + timedelta(days=i)
        key = d.isoformat()
        convs, msgs = by_date.get(key, (0, 0))
        points.append(TrendPoint(date=key, conversations=convs, messages=msgs))
    return points


class DashboardService:
    """Backs the dashboard trends + overview endpoints."""

    OBJECT = "conversations"  # trends reuses the conversations:read guard

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.conversations = ConversationRepository(db)
        self.agents = AgentRepository(db)
        self.customers = CustomerRepository(db)
        self.platform = DashboardRepository(db)

    async def trends(
        self,
        user_id: str,
        tenant_id: str,
        days: int,
        platform_role: str | None = None,
    ) -> DashboardTrends:
        """Daily conversation + message counts for the last ``days`` days.

        Store users are scoped to their tenant (conversations:read); super_admin
        gets the cross-tenant aggregate. ``days`` is clamped to [1, 90].
        """
        days = max(1, min(days, MAX_TREND_DAYS))
        is_super_admin = platform_role == "super_admin"
        if not is_super_admin:
            await permission_service.require(
                user_id,
                tenant_id,
                self.OBJECT,
                "read",
                platform_role=platform_role,
            )
        now = datetime.now(UTC)
        since = now - timedelta(days=days)
        if is_super_admin:
            rows = await self.conversations.daily_trend_all(since)
        else:
            rows = await self.conversations.daily_trend_for_tenant(tenant_id, since)
        points = _fill_continuous(rows, days, now)
        return DashboardTrends(days=days, points=points)

    async def overview(self) -> DashboardOverview:
        """Platform totals + per-tenant conversation activity Top N.

        super_admin-only at the API layer (``require_super_admin``). Activity is
        measured over the last 30 days (matches the plan's "store Top N" panel);
        Top N is capped at 10 (plan §风险).
        """
        since_30d = datetime.now(UTC) - timedelta(days=30)
        tenants = await self.platform.tenant_count()
        users = await self.platform.user_count()
        conversations = await self.conversations.count_all()
        agents = await self.agents.count_all()
        # Customer total = live identities (matches the customers stats card).
        customers_data = await self.customers.statistics_all_global(
            since_7d=datetime.now(UTC) - timedelta(days=7)
        )
        top_rows = await self.conversations.conversation_count_by_tenant(since_30d)
        top_tenants = [
            TenantActivityItem(
                tenant_id=tid, tenant_name=name, conversations=count
            )
            for tid, name, count in top_rows[:10]
        ]
        return DashboardOverview(
            totals=PlatformTotals(
                tenants=tenants,
                users=users,
                conversations=conversations,
                agents=agents,
                customers=customers_data["total"],
            ),
            top_tenants=top_tenants,
        )
