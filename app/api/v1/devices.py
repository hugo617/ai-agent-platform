"""Device endpoints — tenant-scoped device instances.

Reads (``GET /`` and ``GET /{device_id}``) branch in the endpoint body on
the caller's platform role:
- **Cross-tenant viewers** (super_admin / hq_staff) → HQ panorama
  (``DeviceHqRead`` across every tenant). No router-level read guard —
  ``hq_staff`` has no tenant role, so ``require_permission("devices",
  "read")`` would 403 them before the branch. The actual bypass lives in
  ``permission_service.check`` (``hq_staff`` + ``read`` short-circuit +
  ``super_admin`` bypass), reached via the service's within-store path /
  the panorama path skipping ``require`` entirely.
- **Tenant roles** (owner / admin / member) → within-store ``DeviceRead``,
  scoped to the caller's tenant. Permission is enforced inside
  ``DeviceService.list / get`` (``require("devices", "read")``); member
  passes because the default perms grant ``devices:read``.

Writes (POST / PUT / DELETE) keep the router-level
``require_permission("devices", <act>)`` guard — hq_staff / super_admin
without a store role are correctly 403'd there (the HQ viewer is read-only).

Bind / unbind (slice 04) are POST/DELETE on a sub-resource (``/{id}/bind``).
They share the ``require_permission("devices", "update")`` guard (same reason
as PUT — devices is tenant-level, binding is a within-store action). bind
returns **200, not 201**: the device resource already exists, bind is an
assignment; ``DeviceBindResponse.already_bound`` distinguishes "newly bound"
from "idempotent repeat". unbind returns **204 even when no binding exists**
(DELETE idempotency — no 404 for the already-unbound case).
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.core.database import get_db
from app.schemas.device import (
    DeviceBindRequest,
    DeviceBindResponse,
    DeviceCreate,
    DeviceHqRead,
    DeviceRead,
    DeviceUpdate,
)
from app.services.device_service import DeviceService

router = APIRouter(prefix="/devices", tags=["devices"])


# -------------------------------------------------------------------- reads
#
# ``response_model=None`` because the return shape branches on the caller's
# role: ``DeviceRead`` for tenant roles, ``DeviceHqRead`` (a subclass that
# adds ``tenant_name`` / ``model_name`` / ``customer_name``) for cross-tenant
# viewers. Declaring either as the response_model would either drop the
# panorama fields (``DeviceRead``) or pollute the store view with three null
# ``*_name`` keys (``DeviceHqRead``). ``response_model=None`` keeps each
# branch's shape honest; the OpenAPI schema is documented in the docstring.


@router.get("/", response_model=None)
async def list_devices(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DeviceRead] | list[DeviceHqRead]:
    """List devices.

    - super_admin / hq_staff → HQ panorama (``DeviceHqRead``, every tenant).
    - owner / admin / member → this tenant's devices (``DeviceRead``).
    """
    return await DeviceService(db).list(
        user.user_id, user.tenant_id, platform_role=user.platform_role
    )


@router.get("/{device_id}", response_model=None)
async def get_device(
    device_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DeviceRead | DeviceHqRead:
    """Get one device.

    - super_admin / hq_staff → HQ panorama (``DeviceHqRead``, any tenant).
    - owner / admin / member → this tenant's device (``DeviceRead``); a
      foreign tenant's id collapses to 404 (no enumeration leak).
    """
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


# ---------------------------------------------------------- bind (slice 04)


@router.post(
    "/{device_id}/bind",
    response_model=DeviceBindResponse,
    # 200, NOT 201 — the device already exists; bind is an assignment action
    # on a sub-resource, not a resource creation. ``already_bound`` in the
    # body distinguishes "newly bound" from "idempotent repeat".
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("devices", "update"))],
)
async def bind_device_customer(
    device_id: str,
    payload: DeviceBindRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DeviceBindResponse:
    """Bind a device to a customer.

    - Idempotent: binding the device to its *current* customer returns
      ``already_bound: true`` and writes nothing.
    - Overwrite: binding to a *different* customer replaces the previous one
      (``already_bound: false``).
    - ``customer_id`` must have a live ``CustomerProfile`` in the caller's
      tenant, else 400 (nonexistent + cross-tenant both collapse to the same
      400 — no enumeration leak).
    """
    _device, already_bound = await DeviceService(db).bind(
        device_id,
        user.tenant_id,
        payload.customer_id,
        user.user_id,
        platform_role=user.platform_role,
    )
    return DeviceBindResponse(
        device_id=device_id,
        customer_id=payload.customer_id,
        already_bound=already_bound,
    )


@router.delete(
    "/{device_id}/bind",
    # 204 even when the device has no current binding — DELETE is idempotent.
    # Returning 404 for "already unbound" would force clients to GET-then-DELETE.
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("devices", "update"))],
)
async def unbind_device_customer(
    device_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Unbind a device's customer. Idempotent — a device with no binding is a
    no-op, still 204."""
    await DeviceService(db).unbind(
        device_id,
        user.tenant_id,
        user.user_id,
        platform_role=user.platform_role,
    )
