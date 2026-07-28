"""add kind to conversations and fragments to messages

Revision ID: aa7a88a8e643
Revises: 5565cf1e81bd
Create Date: 2026-07-28 10:00:00.000000+00:00

composite-chat (priority 72) slice 01 — data layer. Adds the two columns that
carry composite-conversation state on the existing tables (no new table; the
"add columns not tables" rule, plan §一 Decision 1):

- ``conversations.kind`` (String(16), NOT NULL, server_default 'single').
  Distinguishes a legacy single-agent conversation (``single``, the existing
  /chat/stream path) from a fan-out + synthesize one (``composite``, the new
  /chat/composite path). No index: a "composite-only" filter is not a current
  query, so we don't pre-build one (add-on-demand rule).
- ``messages.fragments`` (JSONB, nullable). NULL for ordinary messages (zero
  cost); only the assistant turn of a composite conversation fills it, with
  one entry per fan-out agent. The migration uses ``postgresql.JSONB`` with NO
  ``.with_variant`` — the SQLite variant lives only on the ORM model so the
  in-memory test suite (``Base.metadata.create_all``) works; on Postgres
  ``alembic check`` compares model-vs-DB both as JSONB, so no drift. This
  mirrors the ``b2c3d4e5f6a7`` conversations.tags migration.

The backfill ``UPDATE conversations SET kind='single' WHERE kind IS NULL`` is
a defensive no-op: ``ADD COLUMN ... NOT NULL DEFAULT 'single'`` already
back-fills existing rows on both PG and SQLite (standard ALTER TABLE
semantics). The UPDATE is kept as belt-and-braces — if a future schema
iteration ever drops the server_default, the migration still leaves no NULLs.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "aa7a88a8e643"
down_revision: str | Sequence[str] | None = "5565cf1e81bd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "kind",
            sa.String(length=16),
            server_default="single",
            nullable=False,
        ),
    )
    op.add_column(
        "messages",
        sa.Column(
            "fragments",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    # Defensive backfill (plan §三 Step 3③ requires it). This is a no-op in
    # practice: ADD COLUMN with NOT NULL + server_default='single' already
    # fills existing rows on both PG and SQLite (standard ALTER TABLE
    # semantics), so no row reaches this point with kind IS NULL. Kept as a
    # belt-and-braces guard so the migration still leaves no NULLs even if a
    # later schema edit ever re-introduces a path to NULL.
    op.execute("UPDATE conversations SET kind='single' WHERE kind IS NULL")


def downgrade() -> None:
    op.drop_column("messages", "fragments")
    op.drop_column("conversations", "kind")
