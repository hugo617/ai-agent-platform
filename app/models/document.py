"""ORM models for the knowledge base / RAG pipeline (priority 57).

Two tables:

  - :class:`Document` — a tenant-scoped knowledge document (product manual,
    FAQ, scripts). Soft-deleted via ``is_deleted`` (mirrors Customer/Role). The
    full text is stored in ``content``; ``status`` tracks the embedding
    pipeline (pending → indexed / failed).
  - :class:`DocumentChunk` — a single chunk of a document with its embedding
    vector. Indexed for cosine-similarity retrieval.

**pgvector / dual-DB compatibility.** The ``embedding`` column uses
``Vector(EMBEDDING_DIMENSION).with_variant(JSON, "sqlite")`` so it builds
cleanly on SQLite (the test suite's in-memory DB) while rendering as the
native ``VECTOR(EMBEDDING_DIMENSION)`` type on Postgres. The cosine-distance
operator (``<=>``) only exists on Postgres with the vector extension; SQLite
tests that exercise retrieval mock the embedding layer rather than running
real vector SQL.

The ``CREATE EXTENSION vector`` lives in the migration (Postgres only, gated
by dialect check), not here.

**Dimension is a module constant.** :data:`EMBEDDING_DIMENSION` is the single
source of truth for the embedding vector width. Switching embedding model
(BAAI/bge-m3 = 1024, OpenAI text-embedding-3-small = 1536, etc.) means
changing this constant AND adding a migration that ``ALTER``\\s the
``document_chunks.embedding`` column type + clears any existing
dimension-mismatched chunks. See migration ``change_embedding_dimension_*``.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base

# Embedding vector dimension. BAAI/bge-m3 = 1024 (current default, served via
# local Ollama). To switch models: change this constant AND add a migration
# that ALTERs document_chunks.embedding to the new VECTOR(N) width, plus clears
# any existing chunks (old-dimension vectors are incompatible with the new
# column type and must be re-embedded). Single source of truth — schemas and
# tests reference this constant rather than hardcoding the magic number.
EMBEDDING_DIMENSION = 1024


def _uuid() -> str:
    return uuid.uuid4().hex


class Document(Base):
    """A tenant-scoped knowledge-base document feeding the RAG pipeline.

    Tenant-level: every store manages its own documents (a store never sees
    another store's knowledge). All agents in the tenant share the tenant's
    documents (MVP — no per-agent knowledge base scoping). Soft-deleted via
    ``is_deleted``; deleting a document also drops its chunks (cascade).
    """

    __tablename__ = "documents"
    __table_args__ = (Index("idx_documents_tenant_id", "tenant_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # How the content arrived: "text" (typed in) or "upload" (.txt file).
    source_type: Mapped[str] = mapped_column(String(20), default="text")
    # The full original text. Split into chunks during ingest.
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Denormalized chunk count for cheap list rendering (set after ingest).
    chunk_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )
    # Pipeline state: "pending" (just created), "indexed" (chunked + embedded),
    # "failed" (ingest error). Shown in the UI.
    status: Mapped[str] = mapped_column(String(20), default="pending")
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), index=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Document {self.id} {self.name} status={self.status}>"


class DocumentChunk(Base):
    """A chunk of a :class:`Document` with its embedding vector.

    ``embedding`` is the ``EMBEDDING_DIMENSION``-wide vector (1024 for
    BAAI/bge-m3). On Postgres it's a native ``VECTOR(EMBEDDING_DIMENSION)``
    column supporting cosine-distance retrieval (``embedding <=> query``); on
    SQLite (tests) it degrades to JSON so ``Base.metadata.create_all``
    succeeds — vector queries are exercised on Postgres / mocked in unit
    tests, never run as real vector SQL on SQLite.
    """

    __tablename__ = "document_chunks"
    __table_args__ = (
        Index("idx_document_chunks_document_id", "document_id"),
        Index("idx_document_chunks_tenant_id", "tenant_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Position of this chunk within the source document (0-based).
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Vector(EMBEDDING_DIMENSION) on Postgres; JSON on SQLite (create_all).
    embedding: Mapped[list[float]] = mapped_column(
        Vector(EMBEDDING_DIMENSION).with_variant(JSON, "sqlite"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<DocumentChunk {self.id} doc={self.document_id} idx={self.chunk_index}>"
