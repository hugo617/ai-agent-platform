"""Role management endpoints — list / create / update / delete.

The role ``code`` is the canonical handle (matches the casbin role name for the
three system roles). Read access is required for every endpoint; mutations need
the matching ``roles:*`` permission.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.core.database import get_db
from app.schemas.rbac import (
    RoleCreate,
    RoleLabel,
    RolePermissionGrant,
    RolePermissionRead,
    RoleRead,
    RoleUpdate,
)
from app.services.rbac_service import RbacService

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get(
    "/label",
    response_model=list[RoleLabel],
    dependencies=[Depends(require_permission("roles", "read"))],
)
async def list_role_labels(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RoleLabel]:
    """Lightweight list for dropdown population."""
    return await RbacService(db).labels(
        user.user_id, user.tenant_id, platform_role=user.platform_role
    )


@router.get(
    "/",
    response_model=list[RoleRead],
    dependencies=[Depends(require_permission("roles", "read"))],
)
async def list_roles(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RoleRead]:
    return await RbacService(db).list(
        user.user_id, user.tenant_id, platform_role=user.platform_role
    )


@router.post(
    "/",
    response_model=RoleRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("roles", "create"))],
)
async def create_role(
    payload: RoleCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RoleRead:
    return await RbacService(db).create(
        user.user_id, user.tenant_id, payload, platform_role=user.platform_role
    )


@router.put(
    "/{role_id}",
    response_model=RoleRead,
    dependencies=[Depends(require_permission("roles", "update"))],
)
async def update_role(
    role_id: str,
    payload: RoleUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RoleRead:
    return await RbacService(db).update(
        user.user_id,
        user.tenant_id,
        role_id,
        payload,
        platform_role=user.platform_role,
    )


@router.delete(
    "/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("roles", "delete"))],
)
async def delete_role(
    role_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await RbacService(db).delete(
        user.user_id, user.tenant_id, role_id, platform_role=user.platform_role
    )


# ----- role ↔ permission grants (SCD2 history source; resync casbin) -----


@router.get(
    "/{role_id}/permissions",
    response_model=list[RolePermissionRead],
    dependencies=[Depends(require_permission("roles", "read"))],
)
async def list_role_permissions(
    role_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RolePermissionRead]:
    """Active ``(obj, act)`` grants for a role (current SCD2 state)."""
    return await RbacService(db).list_permissions(
        user.user_id, user.tenant_id, role_id, platform_role=user.platform_role
    )


@router.post(
    "/{role_id}/permissions",
    response_model=RolePermissionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("roles", "update"))],
)
async def grant_role_permission(
    role_id: str,
    payload: RolePermissionGrant,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RolePermissionRead:
    """Grant ``(obj, act)`` to a role — writes SCD2 + resyncs casbin + audits."""
    return await RbacService(db).grant_permission(
        user.user_id,
        user.tenant_id,
        role_id,
        payload,
        platform_role=user.platform_role,
    )


@router.delete(
    "/{role_id}/permissions/{permission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("roles", "update"))],
)
async def revoke_role_permission(
    role_id: str,
    permission_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Revoke a permission from a role — closes SCD2 row + resyncs casbin."""
    await RbacService(db).revoke_permission(
        user.user_id,
        user.tenant_id,
        role_id,
        permission_id,
        platform_role=user.platform_role,
    )
