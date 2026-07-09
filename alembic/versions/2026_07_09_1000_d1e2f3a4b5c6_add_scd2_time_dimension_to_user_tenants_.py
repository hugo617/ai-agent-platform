"""add SCD2 time dimension to user_tenants and role_permissions

Revision ID: d1e2f3a4b5c6
Revises: ce505ae8a1bd
Create Date: 2026-07-09 10:00:00.000000+00:00

Gives the two authorization-chain tables a Slowly Changing Dimension Type 2
(SCD2) time dimension so the authorization history can be reconstructed at any
point in time. This is the concrete build-out of
``docs/auth-history-scd2-plan.md`` and the "权限变更的历史回溯(SCD2)" section
of the RBAC doc.

Constitution (see permission_service.py): history restoration reads the SCD2
tables; realtime enforcement still reads casbin; the SCD2 *current* state
(``valid_to IS NULL``) is the sync source for casbin.

Two tables change:

1. ``user_tenants`` (scenario i: "what role did this user hold at time T?")
   - Add a surrogate ``id`` PK (uuid hex) and demote the old composite
     ``(user_id, tenant_id)`` PK to indexed business keys.
   - Add ``valid_from`` (NOT NULL, backfilled from ``created_at``) and
     ``valid_to`` (nullable; NULL == current).
   - Add a partial UNIQUE index on ``(user_id, tenant_id) WHERE valid_to IS NULL``
     so at most one active membership exists per (user, tenant).

2. ``role_permissions`` (scenario ii: "what permissions did this role have at T?")
   - Add ``valid_from`` / ``valid_to`` (same as above).
   - Replace the plain UNIQUE(tenant_id, role_id, permission_id) with a partial
     unique index scoped to active rows.

Backfill: every existing row becomes a "current" row (valid_to = NULL,
valid_from = its created_at, or now() if created_at is missing). The new ``id``
on user_tenants is generated per-row with a dialect-appropriate UUID expression
(gen_random_uuid() on Postgres, lower(hex(randomblob(16))) on SQLite).

Why batch_alter_table for user_tenants: SQLite cannot DROP a primary key in
place, so the table is recreated. Postgres would support in-place PK changes,
but batch mode works on both and keeps one code path. The partial unique indexes
are created *after* the batch (outside it) so the dual-dialect
postgresql_where / sqlite_where form can be used verbatim.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, Sequence[str], None] = 'ce505ae8a1bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid_default_sql(dialect_name: str) -> str:
    """Dialect-appropriate UUID-hex expression for backfilling the new id."""
    if dialect_name == 'sqlite':
        # 16 random bytes → 32 hex chars (no dashes), matching uuid4().hex shape.
        return "lower(hex(randomblob(16)))"
    # Postgres: gen_random_uuid() is built-in since PG13 (the project pins PG16).
    return "replace(gen_random_uuid()::text, '-', '')"


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # ------------------------------------------------------------------
    # 1) user_tenants: surrogate PK + SCD2 columns.
    # ------------------------------------------------------------------
    # Done in THREE phases so the id backfill has a real column to write to:
    #
    #   phase A (batch): add id (NULLABLE), valid_from (NOT NULL, server_default
    #     now() so the column can be added onto populated rows), valid_to. On
    #     SQLite the batch recreates the table; on PG it ALTERs in place.
    #   phase B (plain SQL): backfill id (a fresh uuid-hex) + valid_from (from
    #     created_at) for every existing row. Now id is non-NULL everywhere.
    #   phase C (batch): make id NOT NULL, drop the old composite PK, set id as
    #     the new PK.
    uuid_expr = _uuid_default_sql(dialect)
    valid_from_coalesce = (
        "COALESCE(created_at, CURRENT_TIMESTAMP)"
        if dialect == 'sqlite'
        else "COALESCE(created_at, now())"
    )

    # ----- phase A: add the three columns -----
    with op.batch_alter_table('user_tenants', schema=None) as batch:
        batch.add_column(sa.Column('id', sa.String(length=32), nullable=True))
        batch.add_column(
            sa.Column(
                'valid_from',
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text('now()'),
            )
        )
        batch.add_column(
            sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True)
        )

    # ----- phase B: backfill existing rows into "current" SCD2 rows -----
    op.execute(
        f"UPDATE user_tenants SET id = {uuid_expr}, "
        f"valid_from = {valid_from_coalesce} WHERE id IS NULL"
    )

    # ----- phase C: promote id to NOT NULL PK, drop old composite PK -----
    with op.batch_alter_table('user_tenants', schema=None) as batch:
        batch.alter_column(
            'id', existing_type=sa.String(length=32), nullable=False
        )
        batch.drop_constraint('user_tenants_pkey', type_='primary')
        batch.create_primary_key('pk_user_tenants', ['id'])

    # Helpful lookup indexes on the (now non-PK) business keys + the partial
    # unique index enforcing "one active membership per (user, tenant)".
    op.create_index('ix_user_tenants_user_id', 'user_tenants', ['user_id'])
    op.create_index('ix_user_tenants_tenant_id', 'user_tenants', ['tenant_id'])
    op.create_index(
        'uq_user_tenants_active',
        'user_tenants',
        ['user_id', 'tenant_id'],
        unique=True,
        postgresql_where='valid_to IS NULL',
        sqlite_where='valid_to IS NULL',
    )

    # ------------------------------------------------------------------
    # 2) role_permissions: add SCD2 columns, swap the unique constraint for a
    #    partial unique index on active rows.
    # ------------------------------------------------------------------
    op.drop_constraint('uq_role_permission_tenant', 'role_permissions', type_='unique')
    op.add_column(
        'role_permissions',
        sa.Column(
            'valid_from',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),
    )
    op.add_column(
        'role_permissions',
        sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        'uq_role_permissions_active',
        'role_permissions',
        ['tenant_id', 'role_id', 'permission_id'],
        unique=True,
        postgresql_where='valid_to IS NULL',
        sqlite_where='valid_to IS NULL',
    )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # ----- revert role_permissions -----
    op.drop_index('uq_role_permissions_active', table_name='role_permissions')
    op.drop_column('role_permissions', 'valid_to')
    op.drop_column('role_permissions', 'valid_from')
    op.create_unique_constraint(
        'uq_role_permission_tenant',
        'role_permissions',
        ['tenant_id', 'role_id', 'permission_id'],
    )

    # ----- revert user_tenants -----
    op.drop_index('uq_user_tenants_active', table_name='user_tenants')
    op.drop_index('ix_user_tenants_tenant_id', table_name='user_tenants')
    op.drop_index('ix_user_tenants_user_id', table_name='user_tenants')

    with op.batch_alter_table('user_tenants', schema=None) as batch:
        # Restore composite PK, drop surrogate id + SCD2 columns.
        batch.drop_constraint('pk_user_tenants', type_='primary')
        batch.create_primary_key('user_tenants_pkey', ['user_id', 'tenant_id'])
        batch.drop_column('valid_to')
        batch.drop_column('valid_from')
        batch.drop_column('id')
