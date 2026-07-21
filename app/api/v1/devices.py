"""Device endpoints — tenant-scoped device instances (slice 01).

Slice 01 implements the within-store CRUD only:
- ``GET    /``          — list this tenant's devices
- ``GET    /{id}``       — get one device
- ``POST   /``           — create a device
- ``PUT    /{id}``       — update a device
- ``DELETE /{id}``       — soft-delete a device

All five are guarded by ``require_permission("devices", <act>)`` at the
router level. This is a temporary simplification — slice 03 will move the
read endpoints to an in-body branch so ``hq_staff`` can use the HQ panorama
path (the router-level guard would 403 hq_staff because they have no tenant
role, and the cross-tenant read bypass lives in
``permission_service.check``, not in ``require_permission``).

Bind/unbind endpoints (slice 04) are not here yet.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.core.database import get_db
from app.schemas.device import DeviceCreate, DeviceRead, DeviceUpdate
from app.services.device_service import DeviceService

router = APIRouter(prefix="/devices", tags=["devices"])


# -------------------------------------------------------------------- reads


@router.get(
    "/",
    response_model=list[DeviceRead],
    dependencies=[Depends(require_permission("devices", "read"))],
)
async def list_devices(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DeviceRead]:
    """List the caller's tenant's devices.

    Cross-tenant viewers (super_admin / hq_staff) currently hit the same
    path — slice 03 will branch them into the HQ panorama.
    """
    return await DeviceService(db).list(
        user.user_id, user.tenant_id, platform_role=user.platform_role
    )


@router.get(
    "/{device_id}",
    response_model=DeviceRead,
    dependencies=[Depends(require_permission("devices", "read"))],
)
async def get_device(
    device_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DeviceRead:
    return await DeviceService(db).get(
        user.user_id,
        user.tenant_id,
        device_id,
        platform_role=user.platform_role,
    )


# ------------------------------------------------------------------- writes


@router.post(
    "/",
    response_model=DeviceRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("devices", "create"))],
)
async def create_device(
    payload: DeviceCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DeviceRead:
    return await DeviceService(db).create(
        user.user_id,
        user.tenant_id,
        payload,
        platform_role=user.platform_role,
    )


@router.put(
    "/{device_id}",
    response_model=DeviceRead,
    dependencies=[Depends(require_permission("devices", "update"))],
)
async def update_device(
    device_id: str,
    payload: DeviceUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DeviceRead:
    return await DeviceService(db).update(
        user.user_id,
        user.tenant_id,
        device_id,
        payload,
        platform_role=user.platform_role,
    )


@router.delete(
    "/{device_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("devices", "delete"))],
)
async def delete_device(
    device_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await DeviceService(db).delete(
        user.user_id,
        user.tenant_id,
        device_id,
        platform_role=user.platform_role,
    )
