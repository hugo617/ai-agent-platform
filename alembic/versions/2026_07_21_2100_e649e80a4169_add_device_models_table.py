"""add device_models table

Revision ID: e649e80a4169
Revises: d6e7f8a9b0c1
Create Date: 2026-07-21 21:00:00.000000+00:00

Adds the ``device_models`` table — the platform-level device catalogue
(no ``tenant_id``, shared across all tenants). Mirrors the Group
convention: writes guarded by ``require_super_admin()``, reads open to
any authenticated user, soft-deleted via ``is_deleted`` + a partial
unique index on ``name`` (so a deleted model's name can be reused).

See ``app/models/device_model.py`` for field semantics; the ``specs``
JSONB stores free-form physical attributes (``form_factor`` is the only
conventionally-used key — drives the device-picker dropdown grouping).

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON


# revision identifiers, used by Alembic.
revision: str = 'e649e80a4169'
down_revision: Union[str, Sequence[str], None] = 'd6e7f8a9b0c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Match the ORM model exactly: JSONB on Postgres, plain JSON on SQLite (used
# by the test suite).
_SpecsJSON = JSONB().with_variant(JSON, "sqlite")


def upgrade() -> None:
    op.create_table(
        'device_models',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('brand', sa.String(length=200), nullable=True),
        sa.Column('supplier', sa.String(length=200), nullable=True),
        sa.Column(
            'unit_cost',
            sa.Numeric(precision=12, scale=2),
            nullable=False,
        ),
        sa.Column(
            'specs',
            _SpecsJSON,
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_device_models_is_deleted'),
        'device_models',
        ['is_deleted'],
        unique=False,
    )
    op.create_index(
        'uq_device_models_name_active',
        'device_models',
        ['name'],
        unique=True,
        postgresql_where=sa.text('is_deleted = false'),
        sqlite_where=sa.text('is_deleted = 0'),
    )


def downgrade() -> None:
    op.drop_index(
        'uq_device_models_name_active',
        table_name='device_models',
        postgresql_where=sa.text('is_deleted = false'),
        sqlite_where=sa.text('is_deleted = 0'),
    )
    op.drop_index(
        op.f('ix_device_models_is_deleted'), table_name='device_models'
    )
    op.drop_table('device_models')
