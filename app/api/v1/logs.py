"""Audit-log read endpoint (``GET /logs``).

SystemLog rows are written by ``LoggingService.record`` after notable admin
actions (user CRUD, login, …). This endpoint exposes them for the audit page
with pagination + multi-dimensional filtering.

Dual-view scope split (mirrors ``/customers/statistics``):

- **Store users** (owner/admin with ``logs:read``): scoped to their own
  tenant. The ``tenant_id`` query param is ignored — they cannot escape their
  own tenant. Multi-tenant isolation is enforced in the Repository layer.
- **Cross-tenant viewers** (super_admin / hq_staff): see all-platform rows by
  default; may optionally pass ``tenant_id`` to filter to one tenant.

The guard is inlined (not a router ``dependencies=``) because the two view
modes need different guards: store mode requires ``logs:read`` while HQ mode
requires a cross-tenant viewer role — a single dependency can't express both.
``permission_service.require`` is called manually for store users; super_admin
bypasses inside ``check`` (its first-line return True).
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user
from app.core.database import get_db
from app.repositories.log import SystemLogRepository
from app.schemas.log import SystemLogListResponse, SystemLogRead
from app.services.permission_service import is_cross_tenant_viewer, permission_service

router = APIRouter(prefix="/logs", tags=["logs"])


def _parse_dt(raw: str | None) -> datetime | None:
    """Parse an ISO-8601 datetime query param. Raises 400 on a bad value.

    Accepted forms include a bare date (``2026-07-01`` → midnight) and a full
    ``2026-07-01T00:00:00``. Naive datetimes are assumed UTC.
    """
    if raw is None:
        return None
    try:
        # ``fromisoformat`` handles both "YYYY-MM-DD" and full datetimes; it
        # rejects empty strings and malformed values with ValueError.
        return datetime.fromisoformat(raw)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"非法时间格式: {raw}",
        ) from e


@router.get(
    "/",
    response_model=SystemLogListResponse,
)
async def list_logs(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Query(
        default=None, description="操作人 user_id 过滤(本租户内)"
    ),
    action: str | None = Query(default=None, description="操作类型,如 create/update/delete"),
    resource_type: str | None = Query(default=None, description="资源类型,如 users/agents"),
    tenant_id: str | None = Query(
        default=None,
        description="仅 super_admin/hq_staff 生效:按租户过滤;省略=全平台",
    ),
    date_from: str | None = Query(default=None, description="起始时间 ISO-8601(含)"),
    date_to: str | None = Query(default=None, description="结束时间 ISO-8601(含)"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> SystemLogListResponse:
    """Paginated, filterable audit-log list.

    Store users see only their tenant's rows; super_admin / hq_staff see all
    rows (optionally narrowed by ``tenant_id``).
    """
    cross_tenant = is_cross_tenant_viewer(user.platform_role)
    if not cross_tenant:
        # Store user: enforce logs:read (super_admin bypasses in check).
        await permission_service.require(
            user.user_id,
            user.tenant_id,
            "logs",
            "read",
            platform_role=user.platform_role,
        )
        scope_tenant: str | None = user.tenant_id
        # A tenant user cannot pass an arbitrary tenant_id to escape scoping.
        scope_user_id = user_id
    else:
        # Cross-tenant viewer (super_admin / hq_staff): optional tenant filter.
        scope_tenant = tenant_id
        scope_user_id = user_id

    repo = SystemLogRepository(db)
    rows, total = await repo.list_logs(
        tenant_id=scope_tenant,
        user_id=scope_user_id,
        action=action or None,
        resource_type=resource_type or None,
        date_from=_parse_dt(date_from),
        date_to=_parse_dt(date_to),
        limit=limit,
        offset=offset,
    )
    return SystemLogListResponse(
        items=[SystemLogRead.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
