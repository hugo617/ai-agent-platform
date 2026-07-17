"""change embedding dimension from 1536 to 1024 (BAAI/bge-m3 via local Ollama)

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-07-17 01:00:00.000000+00:00

Switches the RAG embedding vector width from 1536 (OpenAI
text-embedding-3-small) to 1024 (BAAI/bge-m3, served via a local Ollama
OpenAI-compatible endpoint). This unblocks running the RAG pipeline
end-to-end against a local model when no OpenAI key is available.

Two coordinated changes land in this migration:

  1. **Type change.** ``document_chunks.embedding`` is ``ALTER``\\ ed from
     ``VECTOR(1536)`` to ``VECTOR(1024)``. pgvector's VECTOR type width is not
     autogenerate-detectable, so this is a hand-written ``op.execute`` with
     raw SQL (the standard pgvector ALTER pattern). Gated by dialect check —
     SQLite (the test suite's in-memory DB) never runs this; the ORM column
     uses ``Vector(1024).with_variant(JSON, "sqlite")`` there.

  2. **Data reset.** Existing ``document_chunks`` rows are deleted before the
     type change because the old 1536-dim vectors are incompatible with the
     new 1024-dim column (pgvector would reject the cast). This is safe in the
     dev/demo environment: every existing chunk was produced by the demo seed
     with a placeholder embedding key, so none of them carry real vectors —
     the corresponding ``documents.status`` is ``failed``. After this
     migration, re-run ``seed_demo.py --reset`` (or the knowledge-base UI's
     re-ingest) with a real embedding provider to repopulate chunks at the new
     dimension.

The downgrade restores the column type to ``VECTOR(1536)`` but cannot
resurrect the deleted chunk rows — they must be re-embedded. The
:data:`app.models.document.EMBEDDING_DIMENSION` constant and the
``EffectiveEmbeddingConfig.dimension`` default move in lockstep with this
migration.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, Sequence[str], None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    # SQLite (the test suite) never runs real vector DDL — the ORM column uses
    # a JSON variant there and tests mock the embedding layer. Mirror the
    # dialect guard pattern in f2b3c4d5e6f7 (CREATE EXTENSION vector).
    if bind.dialect.name == "sqlite":
        return

    # 1. Drop existing chunks first: their 1536-dim vectors cannot be cast to
    #    VECTOR(1024) (pgvector would error on the width mismatch). All current
    #    rows are placeholder-key artifacts (documents.status='failed'), so no
    #    real data is lost. The documents themselves stay — they get
    #    re-ingested at the new dimension on the next seed / UI ingest.
    op.execute("DELETE FROM document_chunks")

    # 2. Shrink the column. pgvector exposes VECTOR(N) as a distinct type per
    #    width, so ALTER COLUMN ... TYPE vector(N) is the documented way to
    #    resize. Using raw SQL because alembic autogenerate does not model the
    #    pgvector type and op.alter_column cannot express it.
    op.execute(
        "ALTER TABLE document_chunks ALTER COLUMN embedding TYPE VECTOR(1024)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return

    # Restore the wider type. Note: chunk data deleted in upgrade() is NOT
    # recoverable — re-run the embedding pipeline (seed_demo --reset or the
    # knowledge UI) to repopulate at 1536 dimensions after downgrading.
    op.execute(
        "ALTER TABLE document_chunks ALTER COLUMN embedding TYPE VECTOR(1536)"
    )
