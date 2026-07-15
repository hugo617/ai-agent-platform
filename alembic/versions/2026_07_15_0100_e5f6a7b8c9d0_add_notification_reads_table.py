"""add notification_reads table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-15 01:00:00.000000+00:00

Adds the ``notification_reads`` join table that stores per-user read state for
**broadcast** notifications (``notifications.user_id IS NULL``).

Why this table exists: a broadcast row is shared by every user in a tenant, so
the ``is_read`` flag on the shared row cannot represent one user dismissing it
without flipping it for the whole tenant. Targeted notifications
(``user_id`` set) still use ``notifications.is_read`` (1:1 with the recipient);
only broadcasts get a row here. The mark-read path INSERTs idempotently
(``ON CONFLICT (notification_id, user_id) DO NOTHING``) so re-marking is safe.

The unique constraint + index are declared here AND on the ORM
``__table_args__`` so ``alembic check`` stays in sync (the dashboard task's CI
drift lesson).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notification_reads",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column(
            "notification_id",
            sa.String(length=32),
            sa.ForeignKey("notifications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(length=128),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "read_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "notification_id", "user_id", name="uq_notification_reads_notif_user"
        ),
    )


def downgrade() -> None:
    op.drop_table("notification_reads")
