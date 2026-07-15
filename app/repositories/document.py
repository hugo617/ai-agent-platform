"""Repositories for the knowledge-base tables (Document + DocumentChunk).

``DocumentRepository`` is tenant-scoped with a soft-delete filter (mirrors
``CustomerProfileRepository`` — the base ``TenantScopedRepository`` doesn't
filter on ``is_deleted``). ``DocumentChunkRepository`` is a plain
``BaseRepository`` because chunks are always reached via a document or a
tenant-scoped vector search, never by a bare id lookup.
"""

from __future__ import annotations

from sqlalchemy import delete, select

from app.models.document import Document, DocumentChunk
from app.repositories.base import BaseRepository, TenantScopedRepository


class DocumentRepository(TenantScopedRepository[Document]):
    """Tenant-scoped documents with a soft-delete filter on reads."""

    model = Document

    async def get_for_tenant(self, obj_id: str, tenant_id: str) -> Document | None:
        """A tenant's *live* document by id (filters out soft-deleted)."""
        stmt = select(Document).where(
            Document.id == obj_id,
            Document.tenant_id == tenant_id,
            Document.is_deleted.is_(False),
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list_for_tenant(self, tenant_id: str) -> list[Document]:
        """All live documents in a tenant, newest first."""
        stmt = (
            select(Document)
            .where(
                Document.tenant_id == tenant_id,
                Document.is_deleted.is_(False),
            )
            .order_by(Document.created_at.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())


class DocumentChunkRepository(BaseRepository[DocumentChunk]):
    """Chunks indexed for vector retrieval."""

    model = DocumentChunk

    async def list_for_document(self, document_id: str) -> list[DocumentChunk]:
        """All chunks of a document, in order."""
        stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index.asc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def delete_for_document(self, document_id: str) -> None:
        """Drop every chunk of a document (hard delete — chunks have no soft-delete)."""
        await self.db.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )
        await self.db.flush()

    async def add_many(self, chunks: list[DocumentChunk]) -> None:
        """Bulk-insert chunks (used after batch embedding)."""
        self.db.add_all(chunks)
        await self.db.flush()

    async def search_by_embedding(
        self, *, tenant_id: str, query_embedding: list[float], top_k: int = 4
    ) -> list[tuple[DocumentChunk, float]]:
        """Cosine-distance vector search within a tenant (Postgres only).

        Returns ``(chunk, distance)`` tuples sorted by distance ascending
        (most similar first). Uses the pgvector ``<=>`` operator (cosine
        distance). SQLite has no such operator, so this is never run as real
        SQL on the test DB; retrieval tests mock the service layer instead.
        The distance is surfaced so callers can convert it to a similarity
        score for the debug UI.
        """
        distance = DocumentChunk.embedding.cosine_distance(query_embedding)
        stmt = (
            select(DocumentChunk, distance.label("distance"))
            .where(DocumentChunk.tenant_id == tenant_id)
            .order_by(distance)
            .limit(top_k)
        )
        rows = (await self.db.execute(stmt)).all()
        return [(row[0], float(row[1])) for row in rows]
