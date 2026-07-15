"""add documents and document_chunks (RAG / pgvector)

Revision ID: f2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-07-15 03:00:00.000000+00:00

Adds the knowledge-base tables for the RAG pipeline (priority 57):

  - ``documents`` — tenant-scoped knowledge documents (manuals, FAQs, scripts),
    soft-deleted, with a ``status`` tracking the embedding pipeline.
  - ``document_chunks`` — a chunk of a document plus its 1536-dim embedding
    vector (native ``VECTOR(1536)`` on Postgres).

Postgres only: enables the ``vector`` extension. SQLite has no such extension;
the test suite builds these tables via ``Base.metadata.create_all`` where the
embedding column degrades to JSON (``Vector(1536).with_variant(JSON, "sqlite")``
in the ORM), so vector queries are never run as real SQL on SQLite. The
extension DDL is gated by a dialect check so this migration is a no-op on
non-Postgres backends.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

try:
    from pgvector.sqlalchemy import VECTOR
except ImportError:  # pragma: no cover - pgvector is a pinned dep
    VECTOR = None  # type: ignore[assignment]


# revision identifiers, used by Alembic.
revision: str = 'f2b3c4d5e6f7'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    # Enable the vector extension on Postgres. SQLite (and other non-PG
    # backends) skip this — the ORM uses a JSON variant there and the test
    # suite never runs real vector SQL. Mirrors the dialect-gated pattern in
    # the SCD2 backfill migration.
    if bind.dialect.name != 'sqlite':
        op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    op.create_table(
        'documents',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column(
            'tenant_id',
            sa.String(length=32),
            sa.ForeignKey('tenants.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('source_type', sa.String(length=20), nullable=False, server_default='text'),
        sa.Column('content', sa.Text(), nullable=False, server_default=''),
        sa.Column('chunk_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_documents_tenant_id', 'documents', ['tenant_id'], unique=False)
    # The is_deleted flag is filtered on every list query; index it.
    op.create_index('ix_documents_is_deleted', 'documents', ['is_deleted'], unique=False)

    op.create_table(
        'document_chunks',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column(
            'document_id',
            sa.String(length=32),
            sa.ForeignKey('documents.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'tenant_id',
            sa.String(length=32),
            sa.ForeignKey('tenants.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        # VECTOR(1536) on Postgres. On SQLite this migration never runs
        # (tests use create_all + the JSON variant), so we don't need a
        # .with_variant here — the raw pgvector type is correct for the only
        # backend that executes this DDL.
        sa.Column('embedding', VECTOR(1536), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'idx_document_chunks_document_id', 'document_chunks', ['document_id'], unique=False
    )
    op.create_index(
        'idx_document_chunks_tenant_id', 'document_chunks', ['tenant_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index('idx_document_chunks_tenant_id', table_name='document_chunks')
    op.drop_index('idx_document_chunks_document_id', table_name='document_chunks')
    op.drop_table('document_chunks')
    op.drop_index('ix_documents_is_deleted', table_name='documents')
    op.drop_index('idx_documents_tenant_id', table_name='documents')
    op.drop_table('documents')
