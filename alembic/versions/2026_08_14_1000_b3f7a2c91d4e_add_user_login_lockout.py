"""add user login lockout columns (failed_attempts / locked_until)

Revision ID: b3f7a2c91d4e
Revises: 05fa069297cc
Create Date: 2026-08-14 10:00:00.000000+00:00

rate-limit-login-lockout slice 01 — DB-persisted login lockout (plan:
harness/docs/plan-rate-limit-login-lockout.md §6 切片 01). Two plain scalar
columns on ``users`` so PostgreSQL and SQLite accept the same migration:

1. **users.failed_attempts** — consecutive failed local logins. NOT NULL with
   server_default '0' so ADD COLUMN back-fills existing rows on both backends.
   Incremented only via a single-statement atomic UPDATE
   (UserRepository.record_failed_attempt), never read-modify-write —
   concurrent guesses must not undercount past the lockout threshold.
2. **users.locked_until** — the temporary auto-unlock deadline. Nullable;
   NULL = not locked. Independent of status='locked' (the administrator's
   permanent lock), which this feature deliberately does not touch.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3f7a2c91d4e"
down_revision: str | Sequence[str] | None = "05fa069297cc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "failed_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "users",
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_attempts")
