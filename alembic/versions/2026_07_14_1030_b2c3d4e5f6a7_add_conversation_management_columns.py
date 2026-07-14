"""add tags is_pinned is_starred to conversations

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-14 10:30:00.000000

conversation-management (priority 50): extends the conversations table with the
columns backing the chat-history management UX — tags (categorization), is_pinned
(keep important chats on top), is_starred (favourites).

- ``tags`` mirrors the CustomerProfile.tags dual-DB idiom: JSONB on Postgres so
  ``tags @> ['x']`` contains queries can be GIN-indexed later, plain JSON on
  SQLite so the in-memory test suite works. Default is an empty array ``'[]'``.
- ``is_pinned`` / ``is_starred`` are plain NOT NULL booleans defaulting false.

Only columns are added — no new index — so there is no ORM ``__table_args__``
drift and ``alembic check`` sees model and DB in sync (the dashboard task hit a
CI drift failure by creating a DB index not declared in the model; that's the
trap we're avoiding here).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "is_pinned",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "is_starred",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("conversations", "is_starred")
    op.drop_column("conversations", "is_pinned")
    op.drop_column("conversations", "tags")
