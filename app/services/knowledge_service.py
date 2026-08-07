"""Knowledge service — document CRUD + RAG ingest/retrieve pipeline.

The RAG pipeline (priority 57):

  1. **Ingest** — split ``document.content`` into chunks (recursive character
     splitter), batch-embed them, store as ``DocumentChunk`` rows with their
     vectors, and mark the document ``indexed``.
  2. **Retrieve** — embed the query, run a cosine-similarity search over the
     tenant's chunks, return the top-k with similarity scores.

All data access is tenant-scoped: a store only ingests/retrieves its own
documents (enforced at the repository layer). Permission checks live here per
the project's dual-validation rule (the route guards AND the service checks).

The embedding provider credentials are resolved per-call via
``EmbeddingConfigService.get_effective`` (tenant > platform > env) and handed
to a fresh ``EmbeddingService`` — so which provider serves embeddings is a
runtime decision, never a global setting.
"""

from __future__ import annotations

from datetime import UTC, datetime

from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentChunk
from app.repositories.document import DocumentChunkRepository, DocumentRepository
from app.repositories.group import GroupRepository
from app.schemas.document import (
    DocumentCreate,
    DocumentRead,
    RetrieveHit,
    RetrieveResult,
)
from app.services.embedding_config_service import embedding_config_service
from app.services.embedding_service import EmbeddingService
from app.services.errors import NotFoundError
from app.services.permission_service import (
    is_cross_tenant_viewer,
    is_group_admin,
    permission_service,
)

# Chunking defaults — tuned for short-ish FAQ/manual text. Chinese-friendly
# because the recursive splitter falls back to single-character splitting for
# scripts without whitespace word boundaries.
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


def _to_read(doc: Document) -> DocumentRead:
    return DocumentRead.model_validate(doc)


class KnowledgeService:
    """Tenant-scoped knowledge-base CRUD + ingest/retrieve."""

    OBJECT = "knowledge"

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.docs = DocumentRepository(db)
        self.chunks = DocumentChunkRepository(db)

    # ------------------------------------------------------------- embedding

    async def _embedding_service(self, tenant_id: str) -> EmbeddingService:
        """Build an EmbeddingService from the resolved provider config."""
        cfg = await embedding_config_service.get_effective(self.db, tenant_id)
        return EmbeddingService(
            api_key=cfg.api_key, base_url=cfg.base_url, model=cfg.model
        )

    # ------------------------------------------------------------------ CRUD

    async def list_documents(
        self,
        user_id: str,
        tenant_id: str,
        platform_role: str | None = None,
    ) -> list[DocumentRead]:
        """Tiered list: cross-tenant viewer / group_admin / store (slice 02 G2).

        The role context (``include_all_tenants`` + ``is_group_admin``) is
        resolved here and handed down to ``list_visible_for`` as bools — the
        repo never imports the service layer (AGENTS.md 铁律 #1, mirrors
        ``KnowledgeCategoryService.list``). ``require`` passes ``db=self.db``
        so the foundation's group_admin bypass fires on knowledge reads (G1).
        """
        await permission_service.require(
            user_id, tenant_id, self.OBJECT, "read",
            platform_role=platform_role, db=self.db,
        )
        group_id = await self._group_of(tenant_id)
        is_ga = (
            group_id is not None
            and await is_group_admin(self.db, user_id, group_id)
        )
        docs = await self.docs.list_visible_for(
            tenant_id=tenant_id,
            group_id=group_id,
            include_all_tenants=is_cross_tenant_viewer(platform_role),
            is_group_admin=is_ga,
        )
        return [_to_read(d) for d in docs]

    async def create_document(
        self,
        user_id: str,
        tenant_id: str,
        payload: DocumentCreate,
        platform_role: str | None = None,
    ) -> DocumentRead:
        await permission_service.require(
            user_id, tenant_id, self.OBJECT, "create",
            platform_role=platform_role, db=self.db,
        )
        doc = Document(
            tenant_id=tenant_id,
            name=payload.name,
            source_type=payload.source_type,
            content=payload.content,
            status="pending",
        )
        await self.docs.add(doc)
        await self.db.commit()
        # Ingest inline (MVP — no background task). Failures mark the document
        # ``failed`` rather than raising, so a bad embedding config doesn't
        # leave an orphan row or break the create flow.
        try:
            await self._ingest(doc)
        except Exception:
            doc.status = "failed"
            await self.db.commit()
        # Re-fetch a fresh, fully-loaded row. The commits above expire the ORM
        # object, so ``updated_at`` (set by onupdate) would otherwise trigger a
        # lazy load outside an async context. Mirrors customer_service's
        # commit-then-refetch pattern.
        fresh = await self.docs.get_for_tenant(doc.id, tenant_id)
        return _to_read(fresh or doc)

    async def delete_document(
        self,
        user_id: str,
        tenant_id: str,
        document_id: str,
        platform_role: str | None = None,
    ) -> None:
        await permission_service.require(
            user_id, tenant_id, self.OBJECT, "delete",
            platform_role=platform_role, db=self.db,
        )
        doc = await self.docs.get_for_tenant(document_id, tenant_id)
        if doc is None:
            raise NotFoundError(f"document {document_id} not found in tenant {tenant_id}")
        # Soft-delete the document; hard-delete its chunks (they have no
        # soft-delete state and would otherwise dangle).
        await self.chunks.delete_for_document(document_id)
        doc.is_deleted = True
        doc.deleted_at = datetime.now(UTC)
        await self.db.commit()

    # ------------------------------------------------------------- pipeline

    async def _ingest(self, doc: Document) -> None:
        """Split, embed, and index a document's content."""
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
        )
        texts = splitter.split_text(doc.content)
        if not texts:
            # Empty after split (e.g. whitespace-only) — nothing to index.
            doc.status = "indexed"
            doc.chunk_count = 0
            await self.db.commit()
            return

        service = await self._embedding_service(doc.tenant_id)
        vectors = await service.embed(texts)

        rows = [
            DocumentChunk(
                document_id=doc.id,
                tenant_id=doc.tenant_id,
                chunk_index=i,
                content=text,
                embedding=vector,
            )
            for i, (text, vector) in enumerate(zip(texts, vectors, strict=True))
        ]
        await self.chunks.add_many(rows)
        doc.status = "indexed"
        doc.chunk_count = len(rows)
        await self.db.commit()

    async def retrieve(
        self,
        query: str,
        tenant_id: str,
        top_k: int = 4,
        *,
        include_distributed: bool = False,
        group_id: str | None = None,
        include_all_tenants: bool = False,
        is_group_admin: bool = False,
    ) -> list[tuple[str, float, str]]:
        """Vector search for the query, three-path by role (slice 02 G3).

        Returns ``(content, similarity, document_id)`` tuples, most similar
        first. Similarity = ``1 - cosine_distance`` (pgvector). Requires
        Postgres — SQLite tests mock this method.

        Role context is handed to ``search_by_embedding`` verbatim (the repo
        owns the WHERE; 铁律 #1). Defaults reproduce the pre-slice-02
        own-store-only behaviour: the debug page calls with all flags default
        (``include_distributed=False``) → own store only. The agent's
        ``retrieve_knowledge`` tool calls with ``include_distributed=True`` →
        own store + docs distributed to it (additive, never drops own hits).
        """
        service = await self._embedding_service(tenant_id)
        query_vec = await service.embed_query(query)
        hits = await self.chunks.search_by_embedding(
            tenant_id=tenant_id,
            query_embedding=query_vec,
            top_k=top_k,
            include_distributed=include_distributed,
            group_id=group_id,
            include_all_tenants=include_all_tenants,
            is_group_admin=is_group_admin,
        )
        # Convert cosine distance to similarity (1.0 = identical direction).
        return [
            (chunk.content, 1.0 - distance, chunk.document_id)
            for chunk, distance in hits
        ]

    async def retrieve_for_debug(
        self,
        user_id: str,
        tenant_id: str,
        query: str,
        top_k: int = 4,
        platform_role: str | None = None,
    ) -> RetrieveResult:
        """Permission-gated retrieval for the debug endpoint (own store only).

        Returns the matched chunks joined with their source document name so
        the admin UI can show "matched from <doc>".

        ``include_distributed`` is left at its default (``False``) so the debug
        page searches ONLY this store's own chunks — distributed docs would
        muddy a "does my pipeline find the right context?" check (plan §4.6 G3
        decision). ``require`` passes ``db=self.db`` so the group_admin bypass
        fires on knowledge reads (G1).
        """
        await permission_service.require(
            user_id, tenant_id, self.OBJECT, "read",
            platform_role=platform_role, db=self.db,
        )
        triples = await self.retrieve(query, tenant_id, top_k=top_k)
        # Batch-resolve document names for the hits. Debug page only returns
        # own-store hits (include_distributed=False), so get_for_tenant suffices.
        doc_ids = list({doc_id for _, _, doc_id in triples})
        doc_names: dict[str, str] = {}
        for did in doc_ids:
            d = await self.docs.get_for_tenant(did, tenant_id)
            if d is not None:
                doc_names[did] = d.name
        hits = [
            RetrieveHit(
                content=content,
                score=score,
                document_id=doc_id,
                document_name=doc_names.get(doc_id, "未知文档"),
            )
            for content, score, doc_id in triples
        ]
        return RetrieveResult(query=query, hits=hits)

    async def _group_of(self, tenant_id: str) -> str | None:
        """The group a tenant belongs to, if any (reverse lookup).

        Sibling of ``KnowledgeCategoryService._group_of``: the group_admin
        visibility branch needs the caller's group, derived from tenant_id via
        GroupTenant (1:1 after D8 → at most one).
        """
        groups = await GroupRepository(self.db).list_for_tenant(tenant_id)
        return groups[0].id if groups else None
