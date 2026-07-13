"""Dashboard endpoints — trends (dual view) + HQ overview (super_admin only).

``trends`` backs the activity bar chart on both the store and HQ dashboards:
store users get their tenant's daily conversation/message counts, super_admin
gets the cross-tenant aggregate. Guarded by ``conversations:read`` (reusing the
existing object since trend volume IS conversation/message volume).

``overview`` is super_admin-only: platform totals + per-tenant activity Top N.
Guarded by ``require_super_admin`` — the action crosses all tenants, so a tenant
role must not be enough.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    CurrentUser,
    get_current_user,
    require_permission,
    require_super_admin,
)
from app.core.database import get_db
from app.schemas.dashboard import DashboardOverview, DashboardTrends
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get(
    "/trends",
    response_model=DashboardTrends,
    dependencies=[Depends(require_permission("conversations", "read"))],
)
async def dashboard_trends(
    # No ``ge``/``le`` bounds: the service clamps to [1, 90] (plan §风险: bound
    # the GROUP BY scan). Clamping instead of 422 keeps the chart usable when a
    # caller asks for an out-of-range window — it just caps rather than erroring.
    days: int = Query(default=7),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardTrends:
    """Daily conversation + message counts for the last ``days`` days.

    Store users are scoped to their tenant; super_admin aggregates across every
    tenant. ``days`` is clamped to [1, 90] (plan §风险: bound the GROUP BY scan).
    """
    service = DashboardService(db)
    return await service.trends(
        user.user_id,
        user.tenant_id,
        days=days,
        platform_role=user.platform_role,
    )


@router.get(
    "/overview",
    response_model=DashboardOverview,
    dependencies=[Depends(require_super_admin())],
)
async def dashboard_overview(
    db: AsyncSession = Depends(get_db),
) -> DashboardOverview:
    """Platform totals + per-tenant conversation activity Top N (super_admin)."""
    return await DashboardService(db).overview()
