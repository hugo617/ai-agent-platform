"""DeviceModel endpoints — platform-level device catalogue management.

DeviceModel is a platform-level entity (no tenant_id), so the permission
model is NOT the usual ``require_permission("device_models", act)``:

- **Writes** (create/update/delete): guarded by ``require_super_admin()`` —
  only the platform super admin can reshape the device catalogue.
- **Reads** (list/get): open to any authenticated user; the service splits
  the view (super_admin / hq_staff → full fields incl. ``unit_cost``;
  tenant user → only ``{id, name, specs.form_factor}`` for the
  device-picker dropdown).

``device_models`` is deliberately absent from DEFAULT_*_PERMS and the
casbin seed — tenant roles have no ``device_models:*`` grant, and reads
bypass casbin entirely.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, require_super_admin
from app.core.database import get_db
from app.schemas.device_model import (
    DeviceModelCreate,
    DeviceModelRead,
    DeviceModelUpdate,
)
from app.services.device_model_service import DeviceModelService

router = APIRouter(prefix="/device-models", tags=["device-models"])


# -------------------------------------------------------------------- reads


@router.get(
    "/",
    # response_model deliberately unset: service returns DeviceModelRead for
    # super_admin/hq_staff and DeviceModelPublicRead for tenant users — two
    # different shapes from the same endpoint.
    dependencies=[Depends(get_current_user)],
)
async def list_device_models(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List device models. super_admin / hq_staff get full fields; tenant
    users get the minimal dropdown shape."""
    return await DeviceModelService(db).list(platform_role=user.platform_role)


@router.get(
    "/{model_id}",
    dependencies=[Depends(get_current_user)],
)
async def get_device_model(
    model_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await DeviceModelService(db).get(
        model_id, platform_role=user.platform_role
    )


# ------------------------------------------------------------------- writes


@router.post(
    "/",
    response_model=DeviceModelRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_super_admin())],
)
async def create_device_model(
    payload: DeviceModelCreate,
    db: AsyncSession = Depends(get_db),
) -> DeviceModelRead:
    return await DeviceModelService(db).create(payload)


@router.put(
    "/{model_id}",
    response_model=DeviceModelRead,
    dependencies=[Depends(require_super_admin())],
)
async def update_device_model(
    model_id: str,
    payload: DeviceModelUpdate,
    db: AsyncSession = Depends(get_db),
) -> DeviceModelRead:
    return await DeviceModelService(db).update(model_id, payload)


@router.delete(
    "/{model_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_super_admin())],
)
async def delete_device_model(
    model_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    await DeviceModelService(db).delete(model_id)
