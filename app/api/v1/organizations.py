"""Organization tree endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.core.database import get_db
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationRead,
    OrganizationTreeNode,
    OrganizationUpdate,
)
from app.services.organization_service import OrganizationService

router = APIRouter(prefix="/organizations", tags=["organizations"])


def _bad_request(e: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def _not_found(e: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get(
    "/tree",
    response_model=list[OrganizationTreeNode],
    dependencies=[Depends(require_permission("organizations", "read"))],
)
async def org_tree(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[OrganizationTreeNode]:
    return await OrganizationService(db).tree(user.user_id, user.tenant_id)


@router.get(
    "/",
    response_model=list[OrganizationRead],
    dependencies=[Depends(require_permission("organizations", "read"))],
)
async def list_orgs(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[OrganizationRead]:
    return await OrganizationService(db).list(user.user_id, user.tenant_id)


@router.post(
    "/",
    response_model=OrganizationRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("organizations", "create"))],
)
async def create_org(
    payload: OrganizationCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrganizationRead:
    try:
        return await OrganizationService(db).create(
            user.user_id, user.tenant_id, payload
        )
    except ValueError as e:
        raise _bad_request(e) from e


@router.put(
    "/{org_id}",
    response_model=OrganizationRead,
    dependencies=[Depends(require_permission("organizations", "update"))],
)
async def update_org(
    org_id: str,
    payload: OrganizationUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrganizationRead:
    try:
        return await OrganizationService(db).update(
            user.user_id, user.tenant_id, org_id, payload
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise _not_found(e) from e
        raise _bad_request(e) from e


@router.delete(
    "/{org_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("organizations", "delete"))],
)
async def delete_org(
    org_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await OrganizationService(db).delete(
            user.user_id, user.tenant_id, org_id
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise _not_found(e) from e
        raise _bad_request(e) from e
