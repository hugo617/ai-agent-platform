"""add wallets, wallet_transactions, model_pricing tables

Revision ID: e8f9a0b1c2d3
Revises: b739b2ae902b
Create Date: 2026-07-13 19:00:00.000000+00:00

Token billing core (series 2/4). Three new tables, all additive:

1. ``wallets`` — the prepaid token balance for one tenant. One live wallet per
   tenant (partial unique index on tenant_id among non-deleted rows). The
   ``balance`` is an integer token count; money (cost) is a charge-time
   snapshot stored on usage_events / wallet_transactions, never on the balance.

2. ``wallet_transactions`` — append-only ledger for every wallet mutation
   (recharge / consume / refund / adjust). Each row carries the signed amount
   and the resulting ``balance_after`` so the wallet history is reconstructable.

3. ``model_pricing`` — per-model price per 1k tokens. ``tenant_id IS NULL`` is
   the platform default; a non-null tenant_id is a per-store override.
   Uniqueness is enforced at the service layer (not via a partial unique index)
   because NULLS NOT DISTINCT differs across PG/SQLite — same decision as
   ``llm_configs``.

No existing column or row is touched.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8f9a0b1c2d3'
down_revision: Union[str, Sequence[str], None] = 'b739b2ae902b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- wallets: prepaid token balance, one live row per tenant ---
    op.create_table(
        'wallets',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('balance', sa.Integer(), server_default='0', nullable=False),
        sa.Column('total_recharged', sa.Integer(), server_default='0', nullable=False),
        sa.Column('total_consumed', sa.Integer(), server_default='0', nullable=False),
        sa.Column('low_balance_threshold', sa.Integer(), server_default='0', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    # Partial unique index: one live wallet per tenant; soft-deleted rows exempt.
    op.create_index(
        'uq_wallets_tenant_active',
        'wallets',
        ['tenant_id'],
        unique=True,
        postgresql_where=sa.text('is_deleted = false'),
        sqlite_where=sa.text('is_deleted = 0'),
    )

    # --- wallet_transactions: append-only ledger of every wallet mutation ---
    op.create_table(
        'wallet_transactions',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('wallet_id', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('balance_after', sa.Integer(), nullable=False),
        sa.Column('usage_event_id', sa.String(length=32), nullable=True),
        sa.Column('model', sa.String(length=64), nullable=True),
        sa.Column('remark', sa.Text(), nullable=True),
        sa.Column('operator_id', sa.String(length=128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['operator_id'], ['users.id']),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['usage_event_id'], ['usage_events.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['wallet_id'], ['wallets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_wallet_transactions_wallet_id'), 'wallet_transactions', ['wallet_id'], unique=False)
    op.create_index(op.f('ix_wallet_transactions_tenant_id'), 'wallet_transactions', ['tenant_id'], unique=False)
    op.create_index('idx_wallet_transactions_tenant_created', 'wallet_transactions', ['tenant_id', 'created_at'])
    op.create_index('idx_wallet_transactions_wallet_created', 'wallet_transactions', ['wallet_id', 'created_at'])

    # --- model_pricing: per-model price per 1k tokens (platform + tenant) ---
    op.create_table(
        'model_pricing',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=True),
        sa.Column('model', sa.String(length=64), nullable=False),
        sa.Column('input_price_per_1k', sa.Numeric(precision=10, scale=6), nullable=False),
        sa.Column('output_price_per_1k', sa.Numeric(precision=10, scale=6), nullable=False),
        sa.Column('currency', sa.String(length=8), server_default='CNY', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_model_pricing_tenant_id'), 'model_pricing', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_model_pricing_model'), 'model_pricing', ['model'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_model_pricing_model'), table_name='model_pricing')
    op.drop_index(op.f('ix_model_pricing_tenant_id'), table_name='model_pricing')
    op.drop_table('model_pricing')

    op.drop_index('idx_wallet_transactions_wallet_created', table_name='wallet_transactions')
    op.drop_index('idx_wallet_transactions_tenant_created', table_name='wallet_transactions')
    op.drop_index(op.f('ix_wallet_transactions_tenant_id'), table_name='wallet_transactions')
    op.drop_index(op.f('ix_wallet_transactions_wallet_id'), table_name='wallet_transactions')
    op.drop_table('wallet_transactions')

    op.drop_index('uq_wallets_tenant_active', table_name='wallets')
    op.drop_table('wallets')
