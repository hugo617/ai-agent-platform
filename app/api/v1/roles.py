"""Role management endpoints — list / create / update / delete.

The role ``code`` is the canonical handle (matches the casbin role name for the
three system roles). Read access is required for every endpoint; mutations need
the matching ``roles:*`` permission.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.core.database import get_db
from app.schemas.rbac import RoleCreate, RoleLabel, RoleRead, RoleUpdate
from app.services.rbac_service import RbacService

router = APIRouter(prefix="/roles", tags=["roles"])


def _bad_request(e: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def _not_found(e: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


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
    return await RbacService(db).labels(user.user_id, user.tenant_id)


@router.get(
    "/",
    response_model=list[RoleRead],
    dependencies=[Depends(require_permission("roles", "read"))],
)
async def list_roles(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RoleRead]:
    return await RbacService(db).list(user.user_id, user.tenant_id)


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
    try:
        return await RbacService(db).create(user.user_id, user.tenant_id, payload)
    except ValueError as e:
        raise _bad_request(e) from e


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
    try:
        return await RbacService(db).update(
            user.user_id, user.tenant_id, role_id, payload
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise _not_found(e) from e
        raise _bad_request(e) from e


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
    try:
        await RbacService(db).delete(user.user_id, user.tenant_id, role_id)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise _not_found(e) from e
        raise _bad_request(e) from e
