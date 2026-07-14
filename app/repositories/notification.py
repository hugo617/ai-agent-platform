"""Repository for in-app notifications.

Pure data-access (no business logic — that lives in ``NotificationService``).
Multi-tenant + user isolation is enforced HERE (the project 铁律): a user sees
their own rows + the tenant-wide rows (``user_id IS NULL``) for their tenant.
They never see another tenant's rows, nor another user's targeted rows.

Writes go through ``NotificationService.create``; this repository exposes
filtered reads + the two ``mark_read`` mutations the API needs.
"""

from datetime import UTC

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.repositories.base import BaseRepository


class NotificationRepository(BaseRepository[Notification]):
    """Read/write surface over Notification rows, tenant + user scoped."""

    model = Notification

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def create(self, notification: Notification) -> Notification:
        """Insert + flush a new notification row (caller commits)."""
        self.db.add(notification)
        await self.db.flush()
        await self.db.refresh(notification)
        return notification

    async def list_for_user(
        self,
        *,
        tenant_id: str,
        user_id: str,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Notification], int]:
        """Return ``(rows, total)`` visible to one user in one tenant.

        Visible set = the user's own targeted rows (``user_id == user_id``) PLUS
        tenant-wide broadcasts (``user_id IS NULL``), both within the caller's
        tenant. Newest-first by ``created_at`` with ``id`` as a deterministic
        tiebreaker so pagination is stable when two rows share a timestamp.
        ``limit``/``offset`` apply only to the row query, not the count.
        """
        visible = select(Notification).where(
            Notification.tenant_id == tenant_id,
            or_(
                Notification.user_id == user_id,
                Notification.user_id.is_(None),
            ),
        )
        if unread_only:
            visible = visible.where(Notification.is_read.is_(False))

        rows_stmt = (
            visible.order_by(Notification.created_at.desc(), Notification.id.asc())
            .limit(limit)
            .offset(offset)
        )
        rows = list((await self.db.execute(rows_stmt)).scalars().all())

        count_stmt = select(func.count()).select_from(visible.subquery())
        total = int((await self.db.execute(count_stmt)).scalar_one())
        return rows, total

    async def get_for_user(
        self, notification_id: str, *, tenant_id: str, user_id: str
    ) -> Notification | None:
        """Fetch one notification iff it is visible to the given user.

        Visibility mirrors ``list_for_user``: own row or tenant-wide broadcast,
        within the caller's tenant. Used by mark-read so a user can only flip
        the read flag on notifications they could actually see.
        """
        stmt = select(Notification).where(
            Notification.id == notification_id,
            Notification.tenant_id == tenant_id,
            or_(
                Notification.user_id == user_id,
                Notification.user_id.is_(None),
            ),
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def unread_count(self, *, tenant_id: str, user_id: str) -> int:
        """Count unread notifications visible to the user (own + tenant-wide)."""
        stmt = select(func.count(Notification.id)).where(
            Notification.tenant_id == tenant_id,
            or_(
                Notification.user_id == user_id,
                Notification.user_id.is_(None),
            ),
            Notification.is_read.is_(False),
        )
        return int((await self.db.execute(stmt)).scalar_one())

    async def mark_read(self, notification: Notification) -> Notification:
        """Flip one notification's ``is_read`` to True (caller commits)."""
        notification.is_read = True
        await self.db.flush()
        return notification

    async def mark_all_read(self, *, tenant_id: str, user_id: str) -> int:
        """Mark every unread notification visible to the user as read.

        Bulk UPDATE — returns the number of rows flipped. Covers both the
        user's targeted rows and the tenant-wide broadcasts they can see.
        """
        stmt = (
            update(Notification)
            .where(
                Notification.tenant_id == tenant_id,
                or_(
                    Notification.user_id == user_id,
                    Notification.user_id.is_(None),
                ),
                Notification.is_read.is_(False),
            )
            .values(is_read=True)
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        await self.db.flush()
        return int(result.rowcount or 0)

    async def exists_recent(
        self,
        *,
        tenant_id: str | None,
        type: str,
        within_hours: int,
        user_id: str | None = None,
    ) -> bool:
        """True if a notification of ``type`` was created in the last window.

        Used by the scheduler's balance-warning scan to dedupe: don't re-warn
        the same tenant every cron tick if a warning is still recent. The
        ``user_id`` filter is optional (the scan dedupes at tenant level).
        """
        from datetime import datetime, timedelta

        cutoff = datetime.now(UTC) - timedelta(hours=within_hours)
        stmt = select(Notification.id).where(
            Notification.type == type,
            Notification.created_at >= cutoff,
        )
        if tenant_id is not None:
            stmt = stmt.where(Notification.tenant_id == tenant_id)
        if user_id is not None:
            stmt = stmt.where(Notification.user_id == user_id)
        result = await self.db.execute(stmt.limit(1))
        return result.scalar_one_or_none() is not None
