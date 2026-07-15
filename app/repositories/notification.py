"""Repository for in-app notifications.

Pure data-access (no business logic — that lives in ``NotificationService``).
Multi-tenant + user isolation is enforced HERE (the project 铁律): a user sees
their own rows + the tenant-wide rows (``user_id IS NULL``) for their tenant.
They never see another tenant's rows, nor another user's targeted rows.

Read-state model (two paths):

- **Targeted** notifications (``Notification.user_id`` set): the recipient is
  the only viewer, so the read flag lives on the row's ``is_read`` column.
- **Broadcast** notifications (``Notification.user_id`` NULL): the row is shared
  by every user in the tenant. A per-user read record in ``notification_reads``
  tracks who has dismissed it — flipping ``is_read`` on the shared row would
  mark it read for the whole tenant. The effective read state for a broadcast
  is "a ``notification_reads`` row exists for (notification, this user)".

Both paths are folded into one ``effective_is_read`` expression so the list /
unread queries return the caller's personal view without the service layer
needing to branch.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, literal, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationRead
from app.repositories.base import BaseRepository


def _effective_is_read(viewer_user_id: str):
    """SQL expression: is this notification read *for the given viewer*?

    - Targeted notification (user_id is not null): use the row's ``is_read``.
    - Broadcast (user_id is null): read iff a ``notification_reads`` row exists
      for (this notification, viewer). We detect that with a correlated EXISTS.
    """
    broadcast_read_exists = (
        select(literal(1))
        .select_from(NotificationRead)
        .where(
            NotificationRead.notification_id == Notification.id,
            NotificationRead.user_id == viewer_user_id,
        )
        .exists()
    )
    return case(
        # Targeted → trust the row-level flag (1:1 with the single recipient).
        (Notification.user_id.is_not(None), Notification.is_read),
        # Broadcast → per-user read record.
        else_=broadcast_read_exists,
    )


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

        The returned ``is_read`` reflects the *viewer's* personal read state
        (see ``_effective_is_read``): broadcasts use the per-user
        ``notification_reads`` table, targeted rows use the row flag.
        """
        is_read_expr = _effective_is_read(user_id).label("effective_is_read")
        visible = (
            select(Notification, is_read_expr)
            .where(
                Notification.tenant_id == tenant_id,
                or_(
                    Notification.user_id == user_id,
                    Notification.user_id.is_(None),
                ),
            )
        )
        if unread_only:
            visible = visible.where(_effective_is_read(user_id).is_(False))

        rows_stmt = (
            visible.order_by(Notification.created_at.desc(), Notification.id.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(rows_stmt)
        # Stamp the computed read state onto each ORM object so the schema's
        # ``is_read`` field (from_attributes) serialises the viewer's view, not
        # the row's stored flag (which for broadcasts is always False).
        rows: list[Notification] = []
        for notif, eff_read in result.all():
            notif.is_read = bool(eff_read)
            rows.append(notif)

        count_stmt = select(func.count()).select_from(visible.subquery())
        total = int((await self.db.execute(count_stmt)).scalar_one())
        return rows, total

    async def get_for_user(
        self, notification_id: str, *, tenant_id: str, user_id: str
    ) -> Notification | None:
        """Fetch one notification iff it is visible to the given user.

        Visibility mirrors ``list_for_user``: own row or tenant-wide broadcast,
        within the caller's tenant. Used by mark-read so a user can only flip
        the read flag on notifications they could actually see. The returned
        object's ``is_read`` carries the viewer's effective state.
        """
        is_read_expr = _effective_is_read(user_id).label("effective_is_read")
        stmt = (
            select(Notification, is_read_expr)
            .where(
                Notification.id == notification_id,
                Notification.tenant_id == tenant_id,
                or_(
                    Notification.user_id == user_id,
                    Notification.user_id.is_(None),
                ),
            )
        )
        result = await self.db.execute(stmt)
        row = result.first()
        if row is None:
            return None
        notif, eff_read = row
        notif.is_read = bool(eff_read)
        return notif

    async def unread_count(self, *, tenant_id: str, user_id: str) -> int:
        """Count unread notifications visible to the user (own + tenant-wide)."""
        is_read_expr = _effective_is_read(user_id)
        stmt = (
            select(func.count(Notification.id))
            .where(
                Notification.tenant_id == tenant_id,
                or_(
                    Notification.user_id == user_id,
                    Notification.user_id.is_(None),
                ),
                is_read_expr.is_(False),
            )
        )
        return int((await self.db.execute(stmt)).scalar_one())

    async def mark_read(self, notification: Notification, *, user_id: str) -> None:
        """Flip one notification read *for the viewer* (caller commits).

        - Targeted notification: set the row's ``is_read`` (1:1 with recipient).
        - Broadcast: insert a ``notification_reads`` row for (notification,
          user). Idempotent — re-marking a broadcast already read is a no-op.
        """
        if notification.user_id is not None:
            # Targeted: the row belongs to this single recipient.
            notification.is_read = True
            await self.db.flush()
            return
        # Broadcast: record this user's read (idempotent upsert).
        await self._upsert_read(notification.id, user_id)

    async def mark_all_read(self, *, tenant_id: str, user_id: str) -> int:
        """Mark every unread notification visible to the user as read.

        Two disjoint sets, both within the caller's tenant:
        1. The user's own targeted rows (``user_id == user``) — bulk UPDATE
           ``is_read=True``.
        2. Tenant-wide broadcasts (``user_id IS NULL``) the user hasn't read
           yet — INSERT a ``notification_reads`` row per broadcast (idempotent).

        Returns the total count of newly-read notifications (set 1 rowcount +
        set 2 inserted rows).
        """
        # --- set 1: targeted rows belonging to this user ---
        targeted_stmt = (
            update(Notification)
            .where(
                Notification.tenant_id == tenant_id,
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
            .values(is_read=True)
            .execution_options(synchronize_session=False)
        )
        targeted_result = await self.db.execute(targeted_stmt)
        targeted_count = int(targeted_result.rowcount or 0)
        await self.db.flush()

        # --- set 2: broadcasts not yet read by this user ---
        # Select broadcast ids visible to this tenant that have no read record
        # for this user yet.
        read_exists = (
            select(literal(1))
            .select_from(NotificationRead)
            .where(
                NotificationRead.notification_id == Notification.id,
                NotificationRead.user_id == user_id,
            )
            .exists()
        )
        broadcast_ids_stmt = select(Notification.id).where(
            Notification.tenant_id == tenant_id,
            Notification.user_id.is_(None),
            read_exists.is_(False),
        )
        broadcast_ids = [
            row[0] for row in (await self.db.execute(broadcast_ids_stmt)).all()
        ]
        broadcast_count = 0
        for nid in broadcast_ids:
            inserted = await self._upsert_read(nid, user_id)
            if inserted:
                broadcast_count += 1

        return targeted_count + broadcast_count

    async def _upsert_read(
        self, notification_id: str, user_id: str
    ) -> bool:
        """Insert a per-user read record for a broadcast. Idempotent.

        Returns True if a new row was inserted, False if one already existed.
        Uses ON CONFLICT DO NOTHING so concurrent mark-read calls (e.g. two
        browser tabs) don't race into a unique-violation.
        """
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        dialect = self.db.bind.dialect.name if self.db.bind else "sqlite"
        if dialect == "postgresql":
            stmt = (
                pg_insert(NotificationRead)
                .values(notification_id=notification_id, user_id=user_id)
                .on_conflict_do_nothing(
                    index_elements=["notification_id", "user_id"]
                )
            )
        else:
            # SQLite (tests) + any other dialect — OR IGNORE keeps it idempotent.
            stmt = sqlite_insert(NotificationRead).values(
                notification_id=notification_id, user_id=user_id
            ).prefix_with("OR IGNORE")
        result = await self.db.execute(stmt)
        await self.db.flush()
        # rowcount == 1 means inserted; 0 means conflict-skipped.
        return int(result.rowcount or 0) > 0

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
