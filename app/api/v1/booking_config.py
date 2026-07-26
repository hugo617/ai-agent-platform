"""Booking schedule-grid config endpoints — two-level (platform + tenant) config.

Five endpoints, all under ``/bookings/config``:

  - GET  /platform              — super_admin only (platform-wide row or None)
  - PUT  /platform              — super_admin only (``settings:update`` is tenant-
                                  scoped, so the platform scope is gated on the
                                  stronger ``require_super_admin`` instead)
  - GET  /tenant/{tenant_id}    — the caller's own tenant row or None; super_admin
                                  can read any tenant; cross-tenant store roles → 403
  - PUT  /tenant/{tenant_id}    — upsert one tenant's override (``settings:update``);
                                  cross-tenant store roles → 403; super_admin → 200
  - GET  /effective?tenant_id=  — the resolved three-level fallback for the grid

Permission model (plan §4.3 + D5):

  - **Platform write**: super_admin only. ``settings:update`` is a *tenant*-
    scoped perm (seeded for owner/admin), so it cannot gate the platform scope —
    a tenant owner must NOT reach the platform-default write. Use
    ``require_super_admin`` for both platform GET and PUT (reading the platform
    default is itself a platform-wide action; a store role has no business
    seeing it directly — they see it via ``/effective``).
  - **Tenant write**: ``settings:update``. super_admin short-circuits via the
    casbin bypass; owner/admin of *this* tenant pass; member/customer → 403.
    Cross-tenant writes are blocked in the service body: a store role's
    ``user.tenant_id`` must equal the path ``tenant_id``, else 403.
  - **Effective read**: any role that can read the target tenant's bookings.
    Platform writers (super_admin / hq_staff) MUST carry ``tenant_id`` (the
    target store); store roles MUST NOT carry it (anti-forgery — resolves to
    their own tenant). Mirrors ``resolve_target_tenant`` from the devices/
    bookings write path but in query-param form.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    CurrentUser,
    get_current_user,
    require_permission,
    require_super_admin,
)
from app.core.database import get_db
from app.schemas.booking_config import (
    BookingConfigRead,
    BookingConfigUpsert,
    EffectiveBookingConfig,
)
from app.services.booking_config_service import booking_config_service
from app.services.permission_service import is_platform_writer

router = APIRouter(prefix="/bookings/config", tags=["bookings"])


# --------------------------------------------------------------- platform scope


@router.get(
    "/platform",
    response_model=BookingConfigRead | None,
    dependencies=[Depends(require_super_admin())],
)
async def get_platform_config(
    db: AsyncSession = Depends(get_db),
) -> BookingConfigRead | None:
    """The platform-wide default config (super_admin only). None if unset."""
    return await booking_config_service.get_platform(db)


@router.put(
    "/platform",
    response_model=BookingConfigRead,
    dependencies=[Depends(require_super_admin())],
)
async def upsert_platform_config(
    payload: BookingConfigUpsert,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BookingConfigRead:
    """Create or update the platform-wide default config (super_admin only)."""
    return await booking_config_service.upsert_platform(db, payload, actor_id=user.user_id)


# ----------------------------------------------------------------- tenant scope


def _ensure_tenant_access(user: CurrentUser, tenant_id: str) -> None:
    """Block cross-tenant access for store roles.

    A platform writer (super_admin / hq_staff) can target any tenant. A store
    role (owner / admin / member / customer) can only touch their own tenant —
    a mismatched path ``tenant_id`` is a forgery attempt → 403. Mirrors the
    ``resolve_target_tenant`` rule from the devices/bookings write path.
    """
    if is_platform_writer(user.platform_role):
        return
    if user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权限:只能操作本租户的配置",
        )


@router.get(
    "/tenant/{tenant_id}",
    response_model=BookingConfigRead | None,
    dependencies=[Depends(require_permission("settings", "read"))],
)
async def get_tenant_config(
    tenant_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BookingConfigRead | None:
    """One tenant's override row. None if the tenant uses the platform default.

    super_admin can read any tenant; store roles are pinned to their own.
    """
    _ensure_tenant_access(user, tenant_id)
    return await booking_config_service.get_tenant(db, tenant_id)


@router.put(
    "/tenant/{tenant_id}",
    response_model=BookingConfigRead,
    dependencies=[Depends(require_permission("settings", "update"))],
)
async def upsert_tenant_config(
    tenant_id: str,
    payload: BookingConfigUpsert,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BookingConfigRead:
    """Create or update one tenant's override (upsert).

    ``settings:update`` is seeded for owner/admin; super_admin bypasses casbin.
    Cross-tenant store roles → 403.
    """
    _ensure_tenant_access(user, tenant_id)
    return await booking_config_service.upsert_tenant(
        db, tenant_id, payload, actor_id=user.user_id
    )


# --------------------------------------------------------------- effective read


@router.get(
    "/effective",
    response_model=EffectiveBookingConfig,
)
async def get_effective_config(
    tenant_id: str | None = Query(
        default=None,
        description="目标门店。平台角色必带;门店角色禁带(防伪造)。",
    ),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EffectiveBookingConfig:
    """The resolved three-level fallback config for the grid.

    - Platform writers (super_admin / hq_staff): MUST carry ``tenant_id`` (the
      target store). Missing → 403.
    - Store roles: MUST NOT carry ``tenant_id`` (anti-forgery). The effective
      tenant is always their own. Carrying it → 403.
    """
    if is_platform_writer(user.platform_role):
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="平台角色查询 effective 配置必须指定目标门店(tenant_id)",
            )
        target = tenant_id
    else:
        if tenant_id is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="门店角色不可指定目标租户(tenant_id)",
            )
        target = user.tenant_id
    return await booking_config_service.get_effective(db, target)
