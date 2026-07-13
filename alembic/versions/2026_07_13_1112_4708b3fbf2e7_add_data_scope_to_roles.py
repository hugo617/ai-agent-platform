"""add data_scope to roles

Revision ID: 4708b3fbf2e7
Revises: 84605f063730
Create Date: 2026-07-13 11:12:00.000000+00:00

Row-level data scope (权限重构系列 3/4) on each role: all/tenant/group/self.
NOT NULL with server_default 'tenant' so existing rows backfill to "this
tenant's rows" — identical to the pre-feature behaviour (TenantScopedRepository
already filtered by tenant_id). Enforced at the Repository layer via
DataScopeService; see app/models/rbac.py Role.data_scope.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4708b3fbf2e7'
down_revision: Union[str, Sequence[str], None] = '84605f063730'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default backfills existing role rows with 'tenant' (their current
    # effective behaviour). Mirrors the tenants.status migration pattern; works
    # on both SQLite (tests) and Postgres (prod) — no dialect-specific syntax.
    op.add_column(
        'roles',
        sa.Column('data_scope', sa.String(length=20), nullable=False, server_default='tenant'),
    )


def downgrade() -> None:
    op.drop_column('roles', 'data_scope')
