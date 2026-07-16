"""db design cleanup: dead columns/tables + Agent soft delete + missing FKs

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-07-16 02:00:00.000000+00:00

Aggregates the DB-design review findings (plan-db-revamp-and-scenario-rebuild
§1) into one migration. No backfill is needed: the dataset is rebuilt from
scratch right after this migration (the dev/demo environment is wiped), so
new columns use ``server_default`` and dropped columns/tables lose their data
intentionally.

Changes by finding:
  - S3: ``agents.is_deleted`` + ``agents.deleted_at`` — soft delete so deleting
    an Agent no longer CASCADE-destroys its Conversations / SET NULLs its
    UsageEvents (keeps history joinable).
  - L3: ``messages.status`` (default 'completed') + ``messages.error`` — failed
    assistant turns are now persisted (status='failed') instead of being a
    silent SSE drop.
  - L2: foreign keys that were missing are added —
      ``conversations.user_id`` → users.id (SET NULL; column also made
      nullable), ``usage_events.tenant_id`` → tenants.id (CASCADE),
      ``usage_events.user_id`` → users.id (SET NULL; column also made
      nullable). All referenced column types match (String(128) for user_id
    mirrors users.id; String(32) for tenant_id mirrors tenants.id).
  - M1: drop ``users.metadata`` (the ``info_json`` dead column — zero reads).
  - M2: drop ``permissions.{description,sort_order,status}`` (seed-only table;
    the PermissionItem schema never carried them).
  - M3: drop the ``verification_codes`` table (built but never wired up — no
    repository, no endpoint, no instantiation).
  - M4: drop ``model_pricing.currency`` (MVP charges CNY only; no branch read
    it).
  - M5: drop ``roles.status`` (never filtered/displayed; RoleRead no longer
    carries it).
  - M6: drop ``user_sessions.token_hash`` (written but never read — revocation
    looks up by ``session_id``/jti, not by hash).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4c5d6e7f8a9'
down_revision: Union[str, Sequence[str], None] = 'a3b4c5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --------------------------------------------------------------- S3: Agent soft delete
    op.add_column(
        'agents',
        sa.Column(
            'is_deleted',
            sa.Boolean(),
            server_default=sa.text('false'),
            nullable=False,
        ),
    )
    op.add_column(
        'agents',
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_agents_is_deleted', 'agents', ['is_deleted'])

    # --------------------------------------------------------------- L3: Message status/error
    op.add_column(
        'messages',
        sa.Column(
            'status',
            sa.String(length=20),
            server_default='completed',
            nullable=False,
        ),
    )
    op.add_column(
        'messages', sa.Column('error', sa.Text(), nullable=True)
    )

    # --------------------------------------------------------------- L2: missing foreign keys
    # conversations.user_id: make nullable, then add FK (SET NULL keeps history
    # when a user is deleted). Column type String(128) matches users.id.
    op.alter_column(
        'conversations',
        'user_id',
        existing_type=sa.String(length=128),
        nullable=True,
    )
    op.create_foreign_key(
        'fk_conversations_user_id_users',
        'conversations',
        'users',
        ['user_id'],
        ['id'],
        ondelete='SET NULL',
    )
    # usage_events.tenant_id: add FK (CASCADE). Type String(32) matches tenants.id.
    op.create_foreign_key(
        'fk_usage_events_tenant_id_tenants',
        'usage_events',
        'tenants',
        ['tenant_id'],
        ['id'],
        ondelete='CASCADE',
    )
    # usage_events.user_id: make nullable, then add FK (SET NULL). Type
    # String(128) matches users.id.
    op.alter_column(
        'usage_events',
        'user_id',
        existing_type=sa.String(length=128),
        nullable=True,
    )
    op.create_foreign_key(
        'fk_usage_events_user_id_users',
        'usage_events',
        'users',
        ['user_id'],
        ['id'],
        ondelete='SET NULL',
    )

    # --------------------------------------------------------------- M1: drop users.metadata (info_json)
    op.drop_column('users', 'metadata')

    # --------------------------------------------------------------- M2: drop permissions dead columns
    op.drop_column('permissions', 'description')
    op.drop_column('permissions', 'sort_order')
    op.drop_column('permissions', 'status')

    # --------------------------------------------------------------- M3: drop verification_codes table
    op.drop_index(
        'idx_verification_codes_expires_at', table_name='verification_codes'
    )
    op.drop_table('verification_codes')

    # --------------------------------------------------------------- M4: drop model_pricing.currency
    op.drop_column('model_pricing', 'currency')

    # --------------------------------------------------------------- M5: drop roles.status
    op.drop_column('roles', 'status')

    # --------------------------------------------------------------- M6: drop user_sessions.token_hash
    op.drop_column('user_sessions', 'token_hash')


def downgrade() -> None:
    # Best-effort inverse for dev rollback. Types mirror the original migrations.
    # --- M6
    op.add_column(
        'user_sessions',
        sa.Column('token_hash', sa.String(length=255), nullable=True),
    )
    # --- M5
    op.add_column(
        'roles',
        sa.Column(
            'status',
            sa.String(length=20),
            server_default='active',
            nullable=False,
        ),
    )
    # --- M4
    op.add_column(
        'model_pricing',
        sa.Column(
            'currency',
            sa.String(length=8),
            server_default='CNY',
            nullable=False,
        ),
    )
    # --- M3
    op.create_table(
        'verification_codes',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('code', sa.String(length=10), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column(
            'expires_at', sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('tenant_id', sa.String(length=32), nullable=True),
        sa.Column('ip', sa.String(length=50), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['tenant_id'], ['tenants.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'idx_verification_codes_expires_at',
        'verification_codes',
        ['expires_at'],
    )
    # --- M2
    op.add_column(
        'permissions',
        sa.Column('description', sa.String(length=255), nullable=True),
    )
    op.add_column(
        'permissions',
        sa.Column(
            'sort_order',
            sa.Integer(),
            server_default='0',
            nullable=False,
        ),
    )
    op.add_column(
        'permissions',
        sa.Column(
            'status',
            sa.String(length=20),
            server_default='active',
            nullable=False,
        ),
    )
    # --- M1
    op.add_column(
        'users',
        sa.Column(
            'metadata',
            sa.JSON().with_variant(sa.JSON(), 'sqlite'),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )
    # --- L2 (drop FKs first, restore nullability)
    op.drop_constraint(
        'fk_usage_events_user_id_users', 'usage_events', type_='foreignkey'
    )
    op.alter_column(
        'usage_events',
        'user_id',
        existing_type=sa.String(length=128),
        nullable=False,
    )
    op.drop_constraint(
        'fk_usage_events_tenant_id_tenants',
        'usage_events',
        type_='foreignkey',
    )
    op.drop_constraint(
        'fk_conversations_user_id_users',
        'conversations',
        type_='foreignkey',
    )
    op.alter_column(
        'conversations',
        'user_id',
        existing_type=sa.String(length=128),
        nullable=False,
    )
    # --- L3
    op.drop_column('messages', 'error')
    op.drop_column('messages', 'status')
    # --- S3
    op.drop_index('ix_agents_is_deleted', table_name='agents')
    op.drop_column('agents', 'deleted_at')
    op.drop_column('agents', 'is_deleted')
