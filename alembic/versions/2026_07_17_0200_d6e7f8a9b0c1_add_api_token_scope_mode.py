"""add api_token.scope_mode (fine-grained scope gate)

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-07-17 02:00:00.000000+00:00

Adds the ``scope_mode`` column to ``api_tokens`` and backfills every existing
(pre-scope) row to ``"full"`` — the behaviour-equivalent mode that makes a
token inherit its grantor's CURRENT permissions at check time, matching the
pre-scope behaviour where every token was a full-power credential.

Why ``scope_mode="full"`` for legacy tokens (not ``"restricted" + full scope set``)
-----------------------------------------------------------------------------------
The naive "mark old tokens restricted and dump the full permission catalogue
into ``scopes``" has two correctness problems:

  1. **Privilege escalation.** A token issued by an ``admin`` or ``member``
     would be backfilled with the OWNER permission set, granting permissions
     the issuer never had.
  2. **Point-in-time drift.** The grantor's permissions at backfill time are
     frozen into ``scopes``; if the grantor is later promoted/demoted, the
     token's effective scope wouldn't track. Restricted mode is meant to be a
     *live* intersection, not a snapshot.

``scope_mode="full"`` solves both: ``permission_service.check`` skips the
scope gate entirely for full-mode tokens and falls through to the grantor's
current casbin/role state, so the token's effective permissions always track
the grantor. The ``scopes`` column is left as-is (``[]`` for legacy tokens)
because full mode never reads it; it's purely informational there.

Idempotency / re-entrancy
-------------------------
The server_default ``"restricted"`` means freshly-added rows start as
restricted; the backfill WHERE clause targets exactly those (``scope_mode =
'restricted' AND scopes = '[]'``). After the backfill, ``scope_mode`` flips
to ``"full"`` and the WHERE no longer matches, so re-running the migration
is a no-op. New tokens created after this migration land with whatever
scope_mode the API request specified (default ``"restricted"``), and only
legacy empty-scope rows get bulk-promoted to full.

The dialect guard mirrors the embedding migration: SQLite (the test suite)
uses ``Base.metadata.create_all`` rather than Alembic, so the column already
exists there and the DDL is skipped.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d6e7f8a9b0c1"
down_revision: Union[str, Sequence[str], None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    # SQLite (the test suite) builds the schema from Base.metadata.create_all,
    # so the column already exists there — skip the DDL entirely. Mirror the
    # dialect guard pattern in c5d6e7f8a9b0 (embedding dimension).
    if bind.dialect.name == "sqlite":
        return

    # 1. Add the column with server_default 'restricted' so NOT NULL is
    #    satisfied for existing rows without a separate backfill of the column
    #    itself. (Existing rows pick up 'restricted' as their initial value.)
    op.add_column(
        "api_tokens",
        sa.Column(
            "scope_mode",
            sa.String(length=16),
            nullable=False,
            server_default="restricted",
        ),
    )

    # 2. Promote every legacy (pre-scope) token to 'full'. The WHERE clause
    #    identifies legacy rows precisely: they were created before this
    #    migration with no scopes selected (the old UI/CLI never sent scopes).
    #    New post-migration tokens keep their explicit scope_mode.
    #
    #    This is the only behaviour-equivalent backfill — see the module
    #    docstring for why "restricted + full scope set" would be wrong.
    op.execute(
        "UPDATE api_tokens SET scope_mode = 'full' "
        "WHERE scope_mode = 'restricted' AND scopes = '[]'"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return

    op.drop_column("api_tokens", "scope_mode")
