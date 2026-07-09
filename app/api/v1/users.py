"""User management endpoints — full profile CRUD with pagination/filtering.

Distinct from ``members.py`` (which manages the user↔tenant *membership* and
roles). Here a "user" is a person with a profile (username/email/phone/…). Each
operation is scoped to the caller's tenant and guarded by casbin.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.core.database import get_db
from app.repositories.user import UserFilters
from app.schemas.user import (
    PasswordReset,
    UserCreate,
    UserListResponse,
    UserRead,
    UserStatistics,
    UserStatusUpdate,
    UserUpdate,
)
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


def _bad_request(e: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def _not_found(e: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get(
    "/statistics",
    response_model=UserStatistics,
    dependencies=[Depends(require_permission("users", "read"))],
)
async def user_statistics(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserStatistics:
    """Aggregate counts for the dashboard cards."""
    return await UserService(db).statistics(
        user.user_id, user.tenant_id, platform_role=user.platform_role
    )


@router.get(
    "/",
    response_model=UserListResponse,
    dependencies=[Depends(require_permission("users", "read"))],
)
async def list_users(
    search: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    role: str | None = Query(default=None),
    sort_by: str = Query(default="created_at"),
    sort_order: str = Query(default="desc"),
    # Declared as ``str | None`` (not ``int``): some API clients (Apifox, etc.)
    # send ``?page&limit`` with EMPTY values, i.e. the empty string. A bare
    # ``int`` (or even ``int | None``) rejects "" with 422 at parse time. Taking
    # it as a string lets us coerce "" → default below, so all of
    # ``?page``, ``?page=``, and ``?page=2`` work.
    page: str | None = Query(default="1"),
    limit: str | None = Query(default="10"),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserListResponse:
    """Paginated, filterable, sortable user list for the current tenant."""
    try:
        page_n = int(page) if page else 1
        limit_n = int(limit) if limit else 10
    except ValueError:
        page_n, limit_n = 1, 10
    page_n = max(page_n, 1)
    limit_n = max(1, min(limit_n, 100))
    filters = UserFilters(
        search=search or None,
        status=status_filter or None,
        role=role or None,
        sort_by=sort_by or "created_at",
        sort_order=sort_order or "desc",
        page=page_n,
        limit=limit_n,
    )
    return await UserService(db).list(
        user.user_id, user.tenant_id, filters, platform_role=user.platform_role
    )


@router.get(
    "/{user_id}",
    response_model=UserRead,
    dependencies=[Depends(require_permission("users", "read"))],
)
async def get_user(
    user_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserRead:
    try:
        return await UserService(db).get(
            user.user_id, user.tenant_id, user_id, platform_role=user.platform_role
        )
    except ValueError as e:
        raise _not_found(e) from e


@router.post(
    "/",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("users", "create"))],
)
async def create_user(
    payload: UserCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserRead:
    try:
        return await UserService(db).create(user.user_id, user.tenant_id, payload)
    except ValueError as e:
        raise _bad_request(e) from e


@router.put(
    "/{user_id}",
    response_model=UserRead,
    dependencies=[Depends(require_permission("users", "update"))],
)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserRead:
    try:
        return await UserService(db).update(
            user.user_id, user.tenant_id, user_id, payload
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise _not_found(e) from e
        raise _bad_request(e) from e


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("users", "delete"))],
)
async def delete_user(
    user_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await UserService(db).delete(user.user_id, user.tenant_id, user_id)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise _not_found(e) from e
        raise _bad_request(e) from e


@router.patch(
    "/{user_id}/status",
    response_model=UserRead,
    dependencies=[Depends(require_permission("users", "update"))],
)
async def change_user_status(
    user_id: str,
    payload: UserStatusUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserRead:
    try:
        return await UserService(db).change_status(
            user.user_id, user.tenant_id, user_id, payload.status
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise _not_found(e) from e
        raise _bad_request(e) from e


@router.post(
    "/{user_id}/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("users", "update"))],
)
async def reset_password(
    user_id: str,
    payload: PasswordReset,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await UserService(db).reset_password(
            user.user_id,
            user.tenant_id,
            user_id,
            payload,
        )
    except ValueError as e:
        raise _not_found(e) from e
