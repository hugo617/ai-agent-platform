"""add updated_at to conversations

Revision ID: a2b3c4d5e6f7
Revises: 1546b57e8c7b
Create Date: 2026-07-10 12:00:00.000000+00:00

Adds an ``updated_at`` column to the ``conversations`` table so the
conversation list can be ordered by "most recently active" (a conversation
bumps to the top when a new message is appended). Existing rows are
backfilled with their ``created_at`` so the column is non-nullable.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, Sequence[str], None] = '1546b57e8c7b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'conversations',
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column('conversations', 'updated_at')
