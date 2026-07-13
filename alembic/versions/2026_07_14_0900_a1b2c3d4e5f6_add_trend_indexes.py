"""add trend indexes for dashboard

Revision ID: a1b2c3d4e5f6
Revises: f9a0b1c2d4e5
Create Date: 2026-07-14 09:00:00.000000

Dashboard 数据看板 (dashboard-analytics): the ``/dashboard/trends`` endpoint
runs ``WHERE tenant_id=? AND created_at>=? GROUP BY date(created_at)`` over
conversations + messages for the store-level bar chart. Without a composite
index this is a full scan per request; ``(tenant_id, created_at)`` turns it into
an index range scan bounded by the date window. ``days`` is clamped to 90 so the
range is always narrow.

The super_admin cross-tenant variant drops the ``tenant_id`` predicate, so it
keeps using the existing ``created_at`` scan — the plan accepts that (overview
caches / Top N cap mitigate it). These indexes are for the per-tenant hot path.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f9a0b1c2d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_conversations_tenant_created_at",
        "conversations",
        ["tenant_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_messages_tenant_created_at",
        "messages",
        ["tenant_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_messages_tenant_created_at", table_name="messages")
    op.drop_index("ix_conversations_tenant_created_at", table_name="conversations")
