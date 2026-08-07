"""Repositories for the knowledge-base tables (Document + DocumentChunk).

``DocumentRepository`` is tenant-scoped with a soft-delete filter (mirrors
``CustomerProfileRepository`` — the base ``TenantScopedRepository`` doesn't
filter on ``is_deleted``). It also carries ``list_visible_for`` — the
knowledge-tiered three-path visibility query (slice 02 G2), driven by
pre-computed role booleans handed down by the service (the repo stays free of
any service/permission import — AGENTS.md 铁律 #1; mirrors
``KnowledgeCategoryRepository.list_visible``). ``DocumentChunkRepository`` is a
plain ``BaseRepository`` because chunks are always reached via a document or a
tenant-scoped vector search, never by a bare id lookup.
"""

from __future__ import annotations

from sqlalchemy import and_, delete, or_, select

from app.models.document import Document, DocumentChunk
from app.models.group import GroupTenant
from app.models.knowledge_distribution import KnowledgeDistribution
from app.repositories.base import BaseRepository, TenantScopedRepository


def _group_admin_visibility_clause(group_id: str):
    """The group_admin aggregated-chain WHERE, shared by list + search (DRY).

    Returns an ``or_`` predicate over the *Document* columns (both callers
    resolve visibility against the source document — ``list_visible_for`` reads
    Document rows directly; ``search_by_embedding`` JOINs DocumentChunk →
    Document first). The clause is: this group's ``scope='group'`` docs PLUS
    every sibling store's ``scope='store'`` docs in the group (sibling ids via
    a GroupTenant subquery, one round-trip). Lives at module scope (not on the
    repo class) so it has no ``self``/db coupling — it only builds a SQL
    fragment. Used only when ``is_group_admin and group_id is not None``.
    """
    sibling_tenant_ids = select(GroupTenant.tenant_id).where(
        GroupTenant.group_id == group_id
    )
    return or_(
        and_(Document.scope == "group", Document.group_id == group_id),
        and_(
            Document.scope == "store",
            Document.tenant_id.in_(sibling_tenant_ids),
        ),
    )


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
        """All live documents in a tenant, newest first.

        Pre-tiering single-tenant query. Kept for ``retrieve_for_debug``'s name
        resolution and other own-store-only paths; the tiered list goes through
        ``list_visible_for`` (slice 02 G2).
        """
        stmt = (
            select(Document)
            .where(
                Document.tenant_id == tenant_id,
                Document.is_deleted.is_(False),
            )
            .order_by(Document.created_at.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def list_visible_for(
        self,
        *,
        tenant_id: str,
        group_id: str | None = None,
        include_all_tenants: bool = False,
        is_group_admin: bool = False,
    ) -> list[Document]:
        """Live documents visible to the caller, per the three-path rule (G2).

        Three roles, three WHERE branches — the isolation lives here so it never
        depends on the service remembering to filter (AGENTS.md 铁律 #2):

        - cross-tenant viewer (``include_all_tenants``; super_admin / hq_staff)
          → every live document, no tier filter.
        - group_admin (``is_group_admin`` + ``group_id``) → aggregated chain view:
          this group's ``scope='group'`` docs PLUS every sibling store's
          ``scope='store'`` docs in that group (GroupTenant subquery keeps it
          one round-trip; mirrors ``KnowledgeCategoryRepository.list_visible``).
        - store → own ``scope='store'`` docs PLUS docs explicitly distributed to
          this store (active ``knowledge_distribution`` rows). Platform/group
          docs are NOT visible to a store unless distributed to it — a store
          never sees another store's docs by default (cross-tenant isolation
          holds; distribution is the explicit opt-in).

        All branches filter ``is_deleted=False``. ``include_all_tenants`` and
        ``is_group_admin`` are pre-computed booleans the service derives from
        ``platform_role`` / ``is_group_admin(db, …)`` and hands down — this repo
        never imports the service layer (铁律 #1).
        """
        base = select(Document).where(Document.is_deleted.is_(False))

        if include_all_tenants:
            stmt = base
        elif is_group_admin and group_id is not None:
            stmt = base.where(_group_admin_visibility_clause(group_id))
        else:
            # store view: own store docs + docs distributed TO this store.
            # Platform/group docs require an active distribution row to be visible
            # — a store never silently sees another scope's undistributed docs.
            distributed_doc_ids = select(KnowledgeDistribution.source_doc_id).where(
                KnowledgeDistribution.target_tenant_id == tenant_id,
                KnowledgeDistribution.is_active.is_(True),
            )
            stmt = base.where(
                or_(
                    and_(Document.scope == "store", Document.tenant_id == tenant_id),
                    Document.id.in_(distributed_doc_ids),
                )
            )

        stmt = stmt.order_by(Document.created_at.desc())
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
        self,
        *,
        tenant_id: str,
        query_embedding: list[float],
        top_k: int = 4,
        include_distributed: bool = False,
        group_id: str | None = None,
        include_all_tenants: bool = False,
        is_group_admin: bool = False,
    ) -> list[tuple[DocumentChunk, float]]:
        """Cosine-distance vector search, three-path by role (Postgres only).

        Returns ``(chunk, distance)`` tuples sorted by distance ascending
        (most similar first). Uses the pgvector ``<=>`` operator (cosine
        distance). SQLite has no such operator, so this is never run as real
        SQL on the test DB; retrieval tests mock the service layer instead.
        The distance is surfaced so callers can convert it to a similarity
        score for the debug UI.

        Three paths (G3), all carrying ``Document.is_deleted=False`` by joining
        back to the source document (a soft-deleted source's chunks must never
        surface, even via an active distribution row — plan §4.5 risk table):

        - ``include_all_tenants`` (super_admin / hq_staff) → global, no tenant
          filter.
        - ``is_group_admin`` + ``group_id`` → aggregated chain view: chunks of
          this group's ``scope='group'`` docs + chunks of every sibling store's
          ``scope='store'`` docs in that group.
        - store → own ``scope='store'`` chunks. When ``include_distributed=True``
          the store ALSO sees chunks of docs distributed to it (active
          distribution rows) — the agent's retrieve_knowledge path. When False
          (debug page) only own-store chunks. Store retrieval is strictly
          additive (own hits are never dropped when distribution is on) —
          zero negative regression (G3 risk control).

        Defaults reproduce the pre-slice-02 single-tenant behaviour exactly
        (``include_distributed=False`` / no group / no admin), so every existing
        caller — the debug page, seed_demo, the unmodified agent path until
        slice 02 wires ``include_distributed=True`` — keeps its behaviour.
        """
        distance = DocumentChunk.embedding.cosine_distance(query_embedding)
        stmt = select(DocumentChunk, distance.label("distance"))

        # Always join the source document so soft-deleted sources are excluded
        # even when reached via a distribution row (plan §4.5 risk table).
        stmt = stmt.join(Document, Document.id == DocumentChunk.document_id).where(
            Document.is_deleted.is_(False)
        )

        if include_all_tenants:
            pass  # global, no tenant filter
        elif is_group_admin and group_id is not None:
            stmt = stmt.where(_group_admin_visibility_clause(group_id))
        else:
            # store: own store's chunks (always).
            tenant_clause = DocumentChunk.tenant_id == tenant_id
            if include_distributed:
                # PLUS chunks of docs distributed TO this store. Reach them via
                # the chunk's document_id matching an active distribution row.
                # Own-store hits are kept (OR, not replace) → additive.
                distributed_doc_ids = select(
                    KnowledgeDistribution.source_doc_id
                ).where(
                    KnowledgeDistribution.target_tenant_id == tenant_id,
                    KnowledgeDistribution.is_active.is_(True),
                )
                tenant_clause = or_(
                    DocumentChunk.tenant_id == tenant_id,
                    DocumentChunk.document_id.in_(distributed_doc_ids),
                )
            stmt = stmt.where(tenant_clause)

        stmt = stmt.order_by(distance).limit(top_k)
        rows = (await self.db.execute(stmt)).all()
        return [(row[0], float(row[1])) for row in rows]
