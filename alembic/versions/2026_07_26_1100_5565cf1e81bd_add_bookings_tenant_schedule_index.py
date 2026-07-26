"""add idx_bookings_tenant_schedule composite index

Revision ID: 5565cf1e81bd
Revises: a1b2c3d4e7g0
Create Date: 2026-07-26 11:00:00.000000+00:00

Adds the ``(tenant_id, scheduled_start_at)`` composite index on ``bookings``
for the HqView per-store schedule-grid endpoint
(plan-booking-schedule-grid.md slice 02).

Why a new index (and not reusing an existing one): the schedule-grid query is
``WHERE tenant_id = ? AND scheduled_start_at >= ? AND scheduled_start_at < ?``.
The existing ``idx_bookings_device_schedule (device_id, scheduled_start_at)``
leads with ``device_id`` so it CANNOT serve a tenant-only predicate — the
planner would fall back to ``idx_bookings_tenant (tenant_id)`` + a filesort on
``scheduled_start_at``. ``idx_bookings_tenant_schedule`` leads with
``tenant_id`` so the same query is one ordered index walk.

Non-unique, non-partial: multiple rows per (tenant_id, scheduled_start_at) are
legal (two devices booked at the same minute). Both PG and SQLite accept
``op.create_index`` identically — no backend-specific DDL, so ``alembic check``
does not drift on either backend. The downgrade mirrors upgrade in full.
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5565cf1e81bd"
down_revision: str | Sequence[str] | None = "a1b2c3d4e7g0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "idx_bookings_tenant_schedule",
        "bookings",
        ["tenant_id", "scheduled_start_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_bookings_tenant_schedule", table_name="bookings"
    )
