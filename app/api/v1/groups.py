"""Group endpoints — cross-tenant business org management.

Group is a platform-level entity (no tenant_id), so the permission model is
NOT the usual ``require_permission("groups", act)``:

- **Writes** (create/update/delete/attach/detach): guarded by
  ``require_super_admin()`` — only the platform super admin can reshape the
  org tree. No tenant role can do this.
- **Reads** (list/get): open to any authenticated user; the service splits the
  view (super_admin → all; tenant user → only their own groups).

``groups`` is deliberately absent from DEFAULT_*_PERMS and the casbin seed —
tenant roles have no ``groups:*`` grant, and reads bypass casbin entirely.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, require_super_admin
from app.core.database import get_db
from app.schemas.group import GroupCreate, GroupRead, GroupUpdate
from app.services.errors import NotFoundError
from app.services.group_service import GroupService

router = APIRouter(prefix="/groups", tags=["groups"])


def _http_exc(e: ValueError) -> HTTPException:
    """Map a service ValueError to the right HTTP status by exception type."""
    if isinstance(e, NotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# -------------------------------------------------------------------- reads


@router.get(
    "/",
    response_model=list[GroupRead],
    dependencies=[Depends(get_current_user)],
)
async def list_groups(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[GroupRead]:
    """List groups. super_admin sees all; tenant users see only their own."""
    return await GroupService(db).list(
        user.tenant_id, platform_role=user.platform_role
    )


@router.get(
    "/{group_id}",
    response_model=GroupRead,
    dependencies=[Depends(get_current_user)],
)
async def get_group(
    group_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GroupRead:
    try:
        return await GroupService(db).get(
            user.tenant_id, group_id, platform_role=user.platform_role
        )
    except ValueError as e:
        raise _http_exc(e) from e


# ------------------------------------------------------------------- writes


@router.post(
    "/",
    response_model=GroupRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_super_admin())],
)
async def create_group(
    payload: GroupCreate,
    db: AsyncSession = Depends(get_db),
) -> GroupRead:
    try:
        return await GroupService(db).create(payload)
    except ValueError as e:
        raise _http_exc(e) from e


@router.put(
    "/{group_id}",
    response_model=GroupRead,
    dependencies=[Depends(require_super_admin())],
)
async def update_group(
    group_id: str,
    payload: GroupUpdate,
    db: AsyncSession = Depends(get_db),
) -> GroupRead:
    try:
        return await GroupService(db).update(group_id, payload)
    except ValueError as e:
        raise _http_exc(e) from e


@router.delete(
    "/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_super_admin())],
)
async def delete_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await GroupService(db).delete(group_id)
    except ValueError as e:
        raise _http_exc(e) from e


# ----------------------------------------------------- tenant attach/detach


@router.post(
    "/{group_id}/tenants/{tenant_id}",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_super_admin())],
)
async def attach_tenant(
    group_id: str,
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await GroupService(db).attach_tenant(group_id, tenant_id)
    except ValueError as e:
        raise _http_exc(e) from e


@router.delete(
    "/{group_id}/tenants/{tenant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_super_admin())],
)
async def detach_tenant(
    group_id: str,
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await GroupService(db).detach_tenant(group_id, tenant_id)
    except ValueError as e:
        raise _http_exc(e) from e
