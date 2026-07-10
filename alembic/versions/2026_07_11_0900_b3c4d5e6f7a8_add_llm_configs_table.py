"""add llm_configs table

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-07-11 09:00:00.000000+00:00

Adds the ``llm_configs`` table for DB-stored LLM provider configuration
(OpenAI-compatible: DeepSeek, OpenAI, Moonshot, ...). A row carries an
encrypted API key, base_url, default model, and the selectable model list.

Two scopes share one table:

  - ``tenant_id IS NULL`` → platform-wide config (super admin), the fallback
    for any tenant without its own row.
  - ``tenant_id = <id>``  → tenant-level override.

Uniqueness is enforced by the service-layer upsert (one active row per scope),
not by a DB constraint — a partial unique index on a nullable ``tenant_id``
needs ``NULLS NOT DISTINCT`` which differs across Postgres/SQLite (dual-DB
rule, see AGENTS.md).

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON


# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, Sequence[str], None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Match the ORM models exactly: JSONB on Postgres, plain JSON on SQLite (used
# by the test suite).
_AvailableModelsJSON = JSONB().with_variant(JSON, "sqlite")


def upgrade() -> None:
    op.create_table(
        'llm_configs',
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
        sa.Column('default_model', sa.String(length=64), nullable=False),
        sa.Column(
            'available_models',
            _AvailableModelsJSON,
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
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
        'ix_llm_configs_tenant_id', 'llm_configs', ['tenant_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_llm_configs_tenant_id', table_name='llm_configs')
    op.drop_table('llm_configs')
