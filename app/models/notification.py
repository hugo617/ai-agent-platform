"""ORM model for in-app notifications.

A ``Notification`` is a short user-facing message surfaced in the top-bar bell
+ the notifications page. Unlike ``SystemLog`` (write-only audit), this is a
read/dismiss surface: every row carries an ``is_read`` flag the user flips.

Targeting:

- ``tenant_id`` scopes a notification to one tenant (NULL = platform-wide, shown
  to every user regardless of tenant).
- ``user_id`` scopes it further to one user within that tenant. NULL means
  "all users in the tenant" — a user sees their own rows + the tenant-wide
  (user_id IS NULL) rows for their tenant.

``type`` is a small enum-ish string: ``balance_warning`` / ``recharge`` /
``role_change`` / ``usage_report`` / ``system``. The frontend picks an icon per
type. ``link`` is an optional in-app path the bell navigates to on click.

No soft-delete: notifications are ephemeral user-facing messages, not
business records. A user "read" them; a cleanup job prunes old read ones later.
Mirrors the append-only simplicity of ``SystemLog`` but with the read flag.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class Notification(Base):
    """One in-app notification row, targeted at a user or a whole tenant."""

    __tablename__ = "notifications"
    __table_args__ = (
        # The list/unread queries filter (tenant_id, user_id, is_read) together,
        # so a composite covering that set keeps the bell dropdown fast as the
        # table grows. These named indexes are declared here AND in the
        # migration so ``alembic check`` sees model and DB in sync (a DB object
        # created by the migration must also live on the ORM — the dashboard
        # task hit a CI drift failure by skipping this).
        Index("ix_notifications_tenant_id", "tenant_id"),
        Index("ix_notifications_user_id", "user_id"),
        Index("ix_notifications_is_read", "is_read"),
        Index("ix_notifications_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
    )
    # NULL = visible to every user in the tenant; a value = one specific user.
    user_id: Mapped[str | None] = mapped_column(
        String(128),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    # balance_warning / recharge / role_change / usage_report / system.
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Optional in-app path the frontend navigates to on click (e.g. "/billing").
    link: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Per-user read flag for TARGETED notifications (user_id is set). For
    # tenant-wide broadcasts (user_id NULL) the read state lives in
    # ``NotificationRead`` instead — a single shared broadcast row must not flip
    # to "read" for the whole tenant when one user dismisses it.
    is_read: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<Notification {self.id} type={self.type} "
            f"tenant={self.tenant_id} user={self.user_id} read={self.is_read}>"
        )


class NotificationRead(Base):
    """Per-user "I read this broadcast" record.

    Broadcast notifications (``Notification.user_id IS NULL``) are shared across
    every user in a tenant — one row, many viewers. Storing the read flag on the
    shared row would make one user's "mark read" flip it for everyone. This
    join table holds one row per (broadcast notification, user) pair so each
    user's read state is independent.

    Targeted notifications (``Notification.user_id`` set) do NOT get a row here
    — they keep using ``Notification.is_read`` since the row is already
    1:1 with the single recipient.
    """

    __tablename__ = "notification_reads"
    __table_args__ = (
        # One read record per (notification, user) — the upsert mark-read path
        # relies on this to be idempotent (INSERT ... ON CONFLICT DO NOTHING).
        UniqueConstraint(
            "notification_id", "user_id", name="uq_notification_reads_notif_user"
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    notification_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("notifications.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<NotificationRead notif={self.notification_id} user={self.user_id}>"
