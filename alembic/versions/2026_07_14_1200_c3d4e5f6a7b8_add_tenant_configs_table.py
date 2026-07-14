"""add tenant_configs table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-14 12:00:00.000000+00:00

Adds the ``tenant_configs`` table for per-tenant white-label branding
(priority 52): display name (overrides the default tenant name in the top bar),
logo URL, theme color (applied globally via the ``--primary`` CSS variable),
and login-page text.

One row per tenant, enforced by ``uq_tenant_config_tenant`` — a plain
UniqueConstraint on the non-nullable ``tenant_id`` (not a partial index). The
constraint is declared in the ORM ``__table_args__`` too, so ``alembic check``
sees model and DB in sync (the dashboard task hit a CI drift failure by
creating a DB object not declared in the model; that's the trap avoided here).

No soft-delete columns: branding is a live config table, matching the
``llm_configs`` / ``tenants`` convention.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_configs",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column(
            "tenant_id",
            sa.String(length=32),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("display_name", sa.String(length=128), nullable=True),
        sa.Column("logo_url", sa.String(length=255), nullable=True),
        sa.Column("theme_color", sa.String(length=7), nullable=True),
        sa.Column("login_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_config_tenant"),
    )


def downgrade() -> None:
    op.drop_table("tenant_configs")
