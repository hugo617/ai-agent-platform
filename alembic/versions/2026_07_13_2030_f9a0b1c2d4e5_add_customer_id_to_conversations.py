"""add customer_id to conversations

Revision ID: f9a0b1c2d4e5
Revises: e8f9a0b1c2d3
Create Date: 2026-07-13 20:30:00.000000

Token 费用管理系列 3/4 (customer-conversation-link): add an optional
``customer_id`` FK on ``conversations`` so a chat can be attributed to the
customer being served. Nullable + SET NULL — not every conversation is tied
to a customer (staff internal queries), and a hard-deleted customer leaves
the history intact (soft-delete keeps the value for traceability).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f9a0b1c2d4e5"
down_revision: Union[str, Sequence[str], None] = "e8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "customer_id",
            sa.String(length=32),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_conversations_customer_id",
        "conversations",
        ["customer_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_conversations_customer_id_customers",
        "conversations",
        "customers",
        ["customer_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_conversations_customer_id_customers",
        "conversations",
        type_="foreignkey",
    )
    op.drop_index("ix_conversations_customer_id", table_name="conversations")
    op.drop_column("conversations", "customer_id")
