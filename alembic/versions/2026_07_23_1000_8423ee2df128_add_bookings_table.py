"""add bookings table

Revision ID: 8423ee2df128
Revises: a0eaec7aab7c
Create Date: 2026-07-23 10:00:00.000000+00:00

Adds the ``bookings`` table — tenant-scoped device-usage reservations (one
store owns many bookings; each booking reserves a time slot on a device for an
optional customer). This is the device-booking feature's slice 01 (Booking
table + overlap detection + status-guarded CRUD).

Key design points (see plan-device-booking.md §0 decisions + §4.4 checklist):

- **No soft delete** (D8). ``bookings`` has neither ``is_deleted`` nor
  ``deleted_at``; there is no partial unique index and no ``DELETE`` endpoint.
  Cancellation is a status transition (``pending`` → ``cancelled``), which
  keeps the audit row and releases the slot (cancelled/done/no_show don't
  participate in overlap detection).
- **6-state status CHECK** (pending / confirmed / in_service / done /
  cancelled / no_show). This feature only writes pending + cancelled; the
  other four are placeholders for ``device-poweron``'s action endpoints.
- **Time fields built once** (D7): ``scheduled_start_at`` / ``scheduled_end_at``
  NOT NULL (written here) + ``started_at`` / ``ended_at`` / ``feedback``
  nullable (placeholders owned by ``device-poweron``'s /start / /end, so that
  feature ships without a schema migration).
- ``device_id`` → ``devices.id`` ``ondelete=SET NULL`` (dead-bolt today —
  devices are soft-deleted; keeps a historical booking when a device is gone,
  mirroring ``devices.customer_id``).
- ``customer_id`` → ``customers.id`` ``ondelete=SET NULL`` (walk-in bookings
  are NULL here).
- ``tenant_id`` → ``tenants.id`` ``ondelete=CASCADE``.
- ``feedback`` uses the generic SQLAlchemy ``JSON`` type (NOT ``JSONB``) so
  SQLite (the test backend) and PG both accept the same migration. If
  ``device-poweron`` later needs JSONB query performance it can ALTER once.

Four plain (non-unique) indexes, query-pattern driven:
``idx_bookings_tenant`` (list), ``idx_bookings_device_schedule``
(device_id, scheduled_start_at — overlap + schedule grid),
``idx_bookings_customer`` (/me/bookings, slice 04), ``idx_bookings_status``
(filter chips / slot-box).

There is deliberately NO partial unique index: overlap is a runtime business
rule (only active states conflict, enforced in BookingService), not a static
column invariant.

PG + SQLite both: plain indexes are dialect-agnostic, so ``alembic check``
does not drift on either backend. The downgrade mirrors upgrade in full.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '8423ee2df128'
down_revision: str | Sequence[str] | None = 'a0eaec7aab7c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'bookings',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('device_id', sa.String(length=32), nullable=True),
        sa.Column('customer_id', sa.String(length=32), nullable=True),
        sa.Column('created_by', sa.String(length=128), nullable=True),
        sa.Column(
            'status',
            sa.String(length=20),
            server_default='pending',
            nullable=False,
        ),
        sa.Column('scheduled_start_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('scheduled_end_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('feedback', sa.JSON(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['created_by'], ['users.id'],
        ),
        sa.ForeignKeyConstraint(
            ['customer_id'], ['customers.id'], ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['device_id'], ['devices.id'], ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['tenant_id'], ['tenants.id'], ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'in_service', 'done', "
            "'cancelled', 'no_show')",
            name='ck_bookings_status_valid',
        ),
    )
    op.create_index(
        'idx_bookings_tenant',
        'bookings',
        ['tenant_id'],
        unique=False,
    )
    op.create_index(
        'idx_bookings_device_schedule',
        'bookings',
        ['device_id', 'scheduled_start_at'],
        unique=False,
    )
    op.create_index(
        'idx_bookings_customer',
        'bookings',
        ['customer_id'],
        unique=False,
    )
    op.create_index(
        'idx_bookings_status',
        'bookings',
        ['status'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('idx_bookings_status', table_name='bookings')
    op.drop_index('idx_bookings_customer', table_name='bookings')
    op.drop_index('idx_bookings_device_schedule', table_name='bookings')
    op.drop_index('idx_bookings_tenant', table_name='bookings')
    op.drop_table('bookings')
