"""add agent orchestration (is_orchestrator/specialty + agent_specialists)

Revision ID: a3b4c5d6e7f8
Revises: f2b3c4d5e6f7
Create Date: 2026-07-16 01:00:00.000000+00:00

Multi-Agent orchestration (priority 58):

  - ``agents.is_orchestrator`` — flags an Agent as a supervisor that routes
    user messages to its attached specialists rather than answering directly.
    ``server_default='false'`` backfills existing rows so they stay regular
    agents (zero behavior change on upgrade).
  - ``agents.specialty`` — free-text role description the supervisor LLM reads
    to decide which specialist should handle a request. Nullable; only
    meaningful for specialists.
  - ``agent_specialists`` — stateless M2M join (orchestrator_id, specialist_id).
    Both FKs CASCADE: deleting either Agent cleans up its memberships. A plain
    UniqueConstraint enforces "at most once" (no soft delete — mirrors
    ``group_tenants``).

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3b4c5d6e7f8'
down_revision: Union[str, Sequence[str], None] = 'f2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ``server_default`` backfills existing rows so every current agent stays
    # a regular (non-orchestrator) agent — zero behavior change on upgrade.
    op.add_column(
        'agents',
        sa.Column(
            'is_orchestrator',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
        ),
    )
    op.add_column(
        'agents',
        sa.Column('specialty', sa.String(length=255), nullable=True),
    )

    op.create_table(
        'agent_specialists',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column(
            'orchestrator_id',
            sa.String(length=32),
            sa.ForeignKey('agents.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'specialist_id',
            sa.String(length=32),
            sa.ForeignKey('agents.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'orchestrator_id', 'specialist_id', name='uq_agent_specialists'
        ),
    )
    op.create_index(
        'idx_agent_specialists_specialist_id',
        'agent_specialists',
        ['specialist_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        'idx_agent_specialists_specialist_id', table_name='agent_specialists'
    )
    op.drop_table('agent_specialists')
    op.drop_column('agents', 'specialty')
    op.drop_column('agents', 'is_orchestrator')
