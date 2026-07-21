"""add devices table

Revision ID: a0eaec7aab7c
Revises: e649e80a4169
Create Date: 2026-07-22 10:00:00.000000+00:00

Adds the ``devices`` table — tenant-scoped device instances (one store owns
many devices; each device instantiates a platform-level ``device_models``
row). Mirrors the customer-profile pattern for tenancy + soft delete, with
two FK dead-bolts worth calling out:

- ``model_id`` → ``device_models.id`` ``ondelete=RESTRICT``. Today
  ``DeviceModelService.delete`` is soft-delete only, so this never fires —
  the *real* guard is ``DeviceService._assert_model_live``. RESTRICT stays
  as a future-proof safety net if a hard-delete endpoint is ever added.
- ``customer_id`` → ``customers.id`` ``ondelete=SET NULL``. Also dead today
  (customers are soft-deleted), kept so a future hard-delete clears the
  binding instead of cascading.

Partial unique index on ``(tenant_id, serial_number)`` among live rows so
serials can be reused after a device is soft-deleted. ``status`` is a
3-state CHECK constraint (active/maintenance/retired) — not a PG ENUM,
so adding a state later doesn't need a dedicated migration.

PG + SQLite both: the partial unique index carries ``postgresql_where`` +
``sqlite_where`` so ``alembic check`` doesn't drift on either backend, and
the downgrade mirrors both for the same reason.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a0eaec7aab7c'
down_revision: Union[str, Sequence[str], None] = 'e649e80a4169'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'devices',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('model_id', sa.String(length=32), nullable=False),
        sa.Column('serial_number', sa.String(length=200), nullable=False),
        sa.Column(
            'status',
            sa.String(length=20),
            server_default='active',
            nullable=False,
        ),
        sa.Column('customer_id', sa.String(length=32), nullable=True),
        sa.Column('created_by', sa.String(length=128), nullable=True),
        sa.Column(
            'is_deleted',
            sa.Boolean(),
            server_default=sa.text('false'),
            nullable=False,
        ),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
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
            ['model_id'], ['device_models.id'], ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['tenant_id'], ['tenants.id'], ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "status IN ('active', 'maintenance', 'retired')",
            name='ck_devices_status_valid',
        ),
    )
    op.create_index(
        op.f('ix_devices_is_deleted'),
        'devices',
        ['is_deleted'],
        unique=False,
    )
    op.create_index(
        'idx_devices_tenant_id',
        'devices',
        ['tenant_id'],
        unique=False,
    )
    op.create_index(
        'uq_devices_tenant_serial_active',
        'devices',
        ['tenant_id', 'serial_number'],
        unique=True,
        postgresql_where=sa.text('is_deleted = false'),
        sqlite_where=sa.text('is_deleted = 0'),
    )


def downgrade() -> None:
    op.drop_index(
        'uq_devices_tenant_serial_active',
        table_name='devices',
        postgresql_where=sa.text('is_deleted = false'),
        sqlite_where=sa.text('is_deleted = 0'),
    )
    op.drop_index(
        'idx_devices_tenant_id', table_name='devices'
    )
    op.drop_index(
        op.f('ix_devices_is_deleted'), table_name='devices'
    )
    op.drop_table('devices')
