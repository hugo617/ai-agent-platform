"""Notification service — read/dismiss surface + best-effort create.

Controller → Service → Repository → Model (the project 铁律). This service is
the single business entry point for notifications:

- ``create`` is called from trigger points (the scheduler's balance-warning
  scan, ``BillingService.recharge``, role-change flows). Like
  ``LoggingService.record`` it is **best-effort**: a notification failure must
  never break the surrounding business transaction, so it runs inside a nested
  SAVEPOINT and any exception is swallowed + logged. A broken notification is a
  UX papercut; a broken recharge is a P0.
- ``list_for_user`` / ``unread_count`` / ``mark_read`` / ``mark_all_read`` back
  the ``/notifications`` read-side API and drive the bell badge.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.repositories.notification import NotificationRepository

logger = logging.getLogger(__name__)


class NotificationService:
    """Business entry point for in-app notifications."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = NotificationRepository(db)

    # --------------------------------------------------------------- writes
    async def create(
        self,
        *,
        type: str,
        title: str,
        content: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
        link: str | None = None,
    ) -> Notification | None:
        """Insert a notification. Never raises — triggers must be safe.

        Runs inside a nested SAVEPOINT so a DB error here rolls back *only* the
        notification insert, leaving the caller's business transaction intact.
        Without this the session would be poisoned and the caller's subsequent
        ``commit()`` would fail with PendingRollbackError — a notification
        failure could break an otherwise-successful recharge.
        """
        try:
            async with self.db.begin_nested():
                return await self.repo.create(
                    Notification(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        type=type,
                        title=title,
                        content=content,
                        link=link,
                    )
                )
        except Exception:  # noqa: BLE001 — triggers must not break the request
            logger.warning(
                "failed to create notification: type=%s tenant=%s",
                type,
                tenant_id,
                exc_info=True,
            )
            return None

    # ---------------------------------------------------------------- reads
    async def list_for_user(
        self,
        *,
        user_id: str,
        tenant_id: str,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Notification], int]:
        return await self.repo.list_for_user(
            tenant_id=tenant_id,
            user_id=user_id,
            unread_only=unread_only,
            limit=limit,
            offset=offset,
        )

    async def unread_count(self, *, user_id: str, tenant_id: str) -> int:
        return await self.repo.unread_count(tenant_id=tenant_id, user_id=user_id)

    # ----------------------------------------------------------- mark reads
    async def mark_read(
        self, *, notification_id: str, user_id: str, tenant_id: str
    ) -> bool:
        """Mark one notification read. Returns False if not found/not owned.

        Ownership is enforced in the repository: a user can only flip the read
        flag on a row they could see (own targeted row or tenant-wide broadcast
        in their tenant). For broadcasts the read is recorded per-user in
        ``notification_reads`` (see ``NotificationRepository.mark_read``).
        Caller commits.
        """
        notification = await self.repo.get_for_user(
            notification_id, tenant_id=tenant_id, user_id=user_id
        )
        if notification is None:
            return False
        if notification.is_read:
            # Already read from this viewer's perspective.
            return True
        await self.repo.mark_read(notification, user_id=user_id)
        await self.db.commit()
        return True

    async def mark_all_read(self, *, user_id: str, tenant_id: str) -> int:
        """Mark every visible unread notification read. Returns count flipped."""
        count = await self.repo.mark_all_read(tenant_id=tenant_id, user_id=user_id)
        await self.db.commit()
        return count
