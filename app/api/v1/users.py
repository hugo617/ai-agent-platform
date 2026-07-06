"""User (tenant member) endpoints — CRUD, all guarded by casbin permissions."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.core.database import get_db
from app.schemas.user import MemberCreate, MemberRead, MemberUpdate
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/",
    response_model=list[MemberRead],
    dependencies=[Depends(require_permission("users", "read"))],
)
async def list_members(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MemberRead]:
    """List all members of the current tenant with their roles."""
    service = UserService(db)
    return await service.list(user.user_id, user.tenant_id)


@router.post(
    "/",
    response_model=MemberRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("users", "create"))],
)
async def add_member(
    payload: MemberCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemberRead:
    """Add a user (by id) to the current tenant with a role."""
    service = UserService(db)
    return await service.add(user.user_id, user.tenant_id, payload)


@router.patch(
    "/{user_id}",
    response_model=MemberRead,
    dependencies=[Depends(require_permission("users", "update"))],
)
async def update_member_role(
    user_id: str,
    payload: MemberUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemberRead:
    """Change a member's role within the current tenant."""
    service = UserService(db)
    try:
        return await service.update_role(user.user_id, user.tenant_id, user_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("users", "delete"))],
)
async def remove_member(
    user_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a member from the current tenant."""
    service = UserService(db)
    try:
        await service.remove(user.user_id, user.tenant_id, user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
