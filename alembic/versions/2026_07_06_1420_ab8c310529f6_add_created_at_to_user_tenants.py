"""add created_at to user_tenants

Revision ID: ab8c310529f6
Revises: 7043d564e936
Create Date: 2026-07-06 14:20:30.625447+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ab8c310529f6'
down_revision: Union[str, Sequence[str], None] = '7043d564e936'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NOTE: casbin_rule is managed by casbin-sqlalchemy-adapter, NOT alembic.
    op.add_column(
        'user_tenants',
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column('user_tenants', 'created_at')
