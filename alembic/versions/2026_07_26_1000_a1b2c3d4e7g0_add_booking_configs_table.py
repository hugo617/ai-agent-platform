"""add booking_configs table

Revision ID: a1b2c3d4e7g0
Revises: 8423ee2df128
Create Date: 2026-07-26 10:00:00.000000+00:00

Adds the ``booking_configs`` table for the HqView schedule-grid's two-level
booking-window config (plan-booking-schedule-grid.md slice 01).

Two scopes share one table, mirroring ``llm_configs`` / ``model_pricing``:

  - ``tenant_id IS NULL`` → platform-wide default (seeded by this migration
    with duration=45 / window 08:00-22:00 so the grid has sane defaults on
    first boot).
  - ``tenant_id = <id>``  → one store's local override.

Uniqueness is enforced by the service-layer upsert (one row per scope), NOT by
a DB constraint — a partial unique index on a nullable ``tenant_id`` would need
``NULLS NOT DISTINCT`` which differs across Postgres/SQLite (dual-DB rule, see
``LlmConfig`` / ``ModelPricing`` for the same decision). There is deliberately
NO ``UNIQUE`` / ``uq_`` / ``create_unique_constraint`` here.

All columns are scalars (``Integer`` / ``String``) — no JSON — so PG and SQLite
both accept the same migration and ``alembic check`` does not drift on either
backend. The downgrade mirrors upgrade in full (drops the table, which also
removes the seeded platform row).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e7g0"
down_revision: str | Sequence[str] | None = "8423ee2df128"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "booking_configs",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column(
            "tenant_id",
            sa.String(length=32),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "default_duration_minutes",
            sa.Integer(),
            server_default=sa.text("45"),
            nullable=False,
        ),
        sa.Column("window_start", sa.String(length=5), nullable=False),
        sa.Column("window_end", sa.String(length=5), nullable=False),
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
    )
    op.create_index(
        "ix_booking_configs_tenant_id",
        "booking_configs",
        ["tenant_id"],
        unique=False,
    )

    # Seed the platform default row (tenant_id IS NULL). The hardcoded defaults
    # match ``app.services.booking_config_service._DEFAULT_*`` so a migrated DB
    # and a fresh-``create_all`` test DB both surface the same window. Idempotent
    # guard: skip if a platform row already exists (re-running upgrade after a
    # partial run, or a deploy that hand-seeded first). Raw INSERT is used
    # because ``op.bulk_insert`` needs a model instance and we want one SQL
    # statement that works on both PG and SQLite.
    op.execute(
        "INSERT INTO booking_configs (id, tenant_id, default_duration_minutes, "
        "window_start, window_end) "
        "SELECT 'platform-default-booking-config', NULL, 45, '08:00', '22:00' "
        "WHERE NOT EXISTS (SELECT 1 FROM booking_configs WHERE tenant_id IS NULL)"
    )


def downgrade() -> None:
    op.drop_index("ix_booking_configs_tenant_id", table_name="booking_configs")
    op.drop_table("booking_configs")
