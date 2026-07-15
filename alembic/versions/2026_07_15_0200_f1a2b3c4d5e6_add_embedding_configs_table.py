"""add embedding_configs table

Revision ID: f1a2b3c4d5e6
Revises: e5f6a7b8c9d0
Create Date: 2026-07-15 02:00:00.000000+00:00

Adds the ``embedding_configs`` table for the RAG pipeline's embeddings provider
config (priority 57). Kept separate from ``llm_configs`` because the embeddings
endpoint differs from the chat LLM — DeepSeek (default chat provider) does NOT
expose an embeddings API, so embeddings must target a different provider
(OpenAI by default).

A row carries an encrypted API key, base_url, and a single model (no selectable
list). Two scopes share one table:

  - ``tenant_id IS NULL`` → platform-wide config (super admin), the fallback
    for any tenant without its own row.
  - ``tenant_id = <id>``  → tenant-level override.

Uniqueness is enforced by the service-layer upsert (one active row per scope),
not by a DB constraint — a partial unique index on a nullable ``tenant_id``
needs ``NULLS NOT DISTINCT`` which differs across Postgres/SQLite (dual-DB
rule, see AGENTS.md). Mirrors the ``llm_configs`` decision.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'embedding_configs',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column(
            'tenant_id',
            sa.String(length=32),
            sa.ForeignKey('tenants.id', ondelete='CASCADE'),
            nullable=True,
        ),
        sa.Column('api_key_encrypted', sa.Text(), nullable=False),
        sa.Column('api_key_hint', sa.String(length=64), nullable=False),
        sa.Column('base_url', sa.String(length=255), nullable=False),
        sa.Column('model', sa.String(length=64), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
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
        'ix_embedding_configs_tenant_id', 'embedding_configs', ['tenant_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_embedding_configs_tenant_id', table_name='embedding_configs')
    op.drop_table('embedding_configs')
