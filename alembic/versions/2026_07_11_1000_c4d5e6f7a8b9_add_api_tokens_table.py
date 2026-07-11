"""add api_tokens table

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-07-11 10:00:00.000000+00:00

Adds the ``api_tokens`` table for long-lived API tokens (PAT / future OAuth).

A row binds a machine credential to its issuer: the token authenticates as
``created_by_user_id`` within a fixed ``tenant_id`` (inherits the issuer's
casbin role, tenant isolation stays intact). The plaintext token is shown only
once at issue time; only a Fernet ciphertext (``token_hash``) plus a short
display prefix are persisted. ``token_type``/``scopes`` are reserved for the
follow-up OAuth + fine-grained-scope tasks.

See ``harness/docs/plan-atoa-api-token-auth.md``.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON


# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, Sequence[str], None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Match the ORM model: JSONB on Postgres, plain JSON on SQLite (tests).
_ScopesJSON = JSONB().with_variant(JSON, "sqlite")


def upgrade() -> None:
    op.create_table(
        'api_tokens',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column(
            'tenant_id',
            sa.String(length=32),
            sa.ForeignKey('tenants.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'created_by_user_id',
            sa.String(length=128),
            sa.ForeignKey('users.id'),
            nullable=False,
        ),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('token_type', sa.String(length=16), nullable=False, server_default='pat'),
        sa.Column('token_hash', sa.Text(), nullable=False),
        sa.Column('token_prefix', sa.String(length=32), nullable=False),
        sa.Column(
            'scopes',
            _ScopesJSON,
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('false')),
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
    op.create_index('ix_api_tokens_tenant_id', 'api_tokens', ['tenant_id'], unique=False)
    op.create_index(
        'ix_api_tokens_created_by_user_id', 'api_tokens', ['created_by_user_id'], unique=False
    )
    op.create_index('ix_api_tokens_token_prefix', 'api_tokens', ['token_prefix'], unique=False)
    op.create_index('ix_api_tokens_is_deleted', 'api_tokens', ['is_deleted'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_api_tokens_is_deleted', table_name='api_tokens')
    op.drop_index('ix_api_tokens_token_prefix', table_name='api_tokens')
    op.drop_index('ix_api_tokens_created_by_user_id', table_name='api_tokens')
    op.drop_index('ix_api_tokens_tenant_id', table_name='api_tokens')
    op.drop_table('api_tokens')
