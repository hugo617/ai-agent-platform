"""In-app notification endpoints (``/notifications``).

Every authenticated user reads/dismisses their OWN notifications. No special
permission is needed — ``get_current_user`` is the only guard. Multi-tenant +
user isolation is enforced in ``NotificationRepository`` (a user sees their own
targeted rows + tenant-wide broadcasts for their tenant, never another user's
rows or another tenant's).

The four endpoints back the top-bar bell (unread-count poll + recent dropdown)
and the full notifications page (paginated list + mark-read actions).
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user
from app.core.database import get_db
from app.schemas.notification import (
    NotificationListResponse,
    NotificationRead,
    UnreadCountResponse,
)
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
)
async def get_unread_count(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UnreadCountResponse:
    """Unread notification count for the bell badge (polled every 30s)."""
    svc = NotificationService(db)
    count = await svc.unread_count(user_id=user.user_id, tenant_id=user.tenant_id)
    return UnreadCountResponse(count=count)


@router.get(
    "/",
    response_model=NotificationListResponse,
)
async def list_notifications(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    unread_only: bool = Query(default=False, description="仅未读"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> NotificationListResponse:
    """Paginated notification list for the current user.

    Returns the user's own targeted notifications plus tenant-wide broadcasts,
    newest-first. ``unread_only`` narrows to unread (bell dropdown view).
    """
    svc = NotificationService(db)
    rows, total = await svc.list_for_user(
        user_id=user.user_id,
        tenant_id=user.tenant_id,
        unread_only=unread_only,
        limit=limit,
        offset=offset,
    )
    return NotificationListResponse(
        items=[NotificationRead.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.put(
    "/read-all",
    response_model=UnreadCountResponse,
)
async def mark_all_read(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UnreadCountResponse:
    """Mark every visible unread notification as read. Returns remaining count."""
    svc = NotificationService(db)
    await svc.mark_all_read(user_id=user.user_id, tenant_id=user.tenant_id)
    count = await svc.unread_count(user_id=user.user_id, tenant_id=user.tenant_id)
    return UnreadCountResponse(count=count)


@router.put(
    "/{notification_id}/read",
    response_model=NotificationRead,
)
async def mark_one_read(
    notification_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationRead:
    """Mark one notification read. 404 if it doesn't exist or isn't yours."""
    svc = NotificationService(db)
    ok = await svc.mark_read(
        notification_id=notification_id,
        user_id=user.user_id,
        tenant_id=user.tenant_id,
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="通知不存在或不属于当前用户",
        )
    notification = await svc.repo.get_for_user(
        notification_id, tenant_id=user.tenant_id, user_id=user.user_id
    )
    # ok=True guarantees the row is visible to the user; the second fetch is
    # only to return the refreshed row via the read schema.
    assert notification is not None  # noqa: S101 — invariant held by mark_read
    return NotificationRead.model_validate(notification)
