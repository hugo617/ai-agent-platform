"""add message token columns and usage_events ledger

Revision ID: b739b2ae902b
Revises: 4708b3fbf2e7
Create Date: 2026-07-13 14:30:00.000000+00:00

Token billing foundation (series 1/4). Two changes:

1. ``messages`` gains four nullable columns — ``prompt_tokens``,
   ``completion_tokens``, ``total_tokens``, ``model`` — so an assistant
   message records how many tokens it consumed and which model served it.
   All nullable (no server_default): user messages and messages persisted
   before this migration simply have NULL, which is the correct "unknown"
   semantic. No backfill needed.

2. New ``usage_events`` table: an append-only ledger with one row per
   successful assistant turn. ``customer_id`` and ``cost`` are nullable now
   (filled by later tasks 2/3); this task records raw token counts only.

Both are additive — no existing column or row is touched.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b739b2ae902b'
down_revision: Union[str, Sequence[str], None] = '4708b3fbf2e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- messages: token + model columns (all nullable, backward compatible) ---
    op.add_column('messages', sa.Column('prompt_tokens', sa.Integer(), nullable=True))
    op.add_column('messages', sa.Column('completion_tokens', sa.Integer(), nullable=True))
    op.add_column('messages', sa.Column('total_tokens', sa.Integer(), nullable=True))
    op.add_column('messages', sa.Column('model', sa.String(length=64), nullable=True))

    # --- usage_events: append-only token usage ledger ---
    op.create_table(
        'usage_events',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('conversation_id', sa.String(length=32), nullable=False),
        sa.Column('message_id', sa.String(length=32), nullable=False),
        sa.Column('agent_id', sa.String(length=32), nullable=True),
        sa.Column('customer_id', sa.String(length=32), nullable=True),
        sa.Column('user_id', sa.String(length=128), nullable=False),
        sa.Column('model', sa.String(length=64), nullable=False),
        sa.Column('prompt_tokens', sa.Integer(), nullable=False),
        sa.Column('completion_tokens', sa.Integer(), nullable=False),
        sa.Column('total_tokens', sa.Integer(), nullable=False),
        sa.Column('cost', sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_usage_events_tenant_id'), 'usage_events', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_usage_events_conversation_id'), 'usage_events', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_usage_events_message_id'), 'usage_events', ['message_id'], unique=False)
    op.create_index('idx_usage_events_tenant_created', 'usage_events', ['tenant_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_usage_events_tenant_created', table_name='usage_events')
    op.drop_index(op.f('ix_usage_events_message_id'), table_name='usage_events')
    op.drop_index(op.f('ix_usage_events_conversation_id'), table_name='usage_events')
    op.drop_index(op.f('ix_usage_events_tenant_id'), table_name='usage_events')
    op.drop_table('usage_events')
    op.drop_column('messages', 'model')
    op.drop_column('messages', 'total_tokens')
    op.drop_column('messages', 'completion_tokens')
    op.drop_column('messages', 'prompt_tokens')
