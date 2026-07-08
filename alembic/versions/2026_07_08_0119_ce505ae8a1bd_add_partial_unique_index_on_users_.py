"""add partial unique index on users.username/email (non-deleted)

Revision ID: ce505ae8a1bd
Revises: c1d2e3f4a5b6
Create Date: 2026-07-08 01:19:38.348405+00:00

Adds partial UNIQUE indexes on users.username and users.email scoped to
non-deleted rows. This enforces uniqueness at the DB layer so the application's
check-then-insert pattern (UserService.create) can't race into a duplicate under
concurrent requests. Soft-deleted rows keep their identifiers and can be reused
by a later account — matching the is_deleted=False filter every lookup already
applies.

Replaces the plain (non-unique) ix_users_username / ix_users_email indexes: a
unique partial index covers equality lookups just as well.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'ce505ae8a1bd'
down_revision: Union[str, Sequence[str], None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the plain indexes created by the previous migration; the unique
    # partial indexes below supersede them.
    op.drop_index('ix_users_username', table_name='users')
    op.drop_index('ix_users_email', table_name='users')

    op.create_index(
        'uq_users_username_active',
        'users',
        ['username'],
        unique=True,
        postgresql_where="is_deleted = false",
        sqlite_where="is_deleted = 0",
    )
    op.create_index(
        'uq_users_email_active',
        'users',
        ['email'],
        unique=True,
        postgresql_where="is_deleted = false",
        sqlite_where="is_deleted = 0",
    )


def downgrade() -> None:
    op.drop_index('uq_users_email_active', table_name='users')
    op.drop_index('uq_users_username_active', table_name='users')
    # Restore the original plain indexes.
    op.create_index('ix_users_username', 'users', ['username'])
    op.create_index('ix_users_email', 'users', ['email'])
