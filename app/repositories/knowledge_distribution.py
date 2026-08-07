"""Repository for ``knowledge_distribution`` (knowledge-tiered Feature B slice 03).

A distribution row is the reference-model link (D4) between a source document
and a target store: "doc X is visible to store Y". It never copies the doc —
``list_visible_for`` / ``search_by_embedding`` reach the source via the row
(slice 02), so edits to the source are immediately visible downstream and a
revoke is a soft flip (``is_active = false``), not a hard delete.

``UniqueConstraint(source_doc_id, target_tenant_id)`` (in the model) enforces
"at most one row per (doc, target)": re-distributing an already-distributed doc
must re-enable the existing row (Feature B's upsert), not insert a duplicate.
``is_active`` is deliberately *outside* the unique key so the (doc, target)
relationship has a single lifecycle row that flips on/off. This repo implements
that upsert in ``create`` (catch IntegrityError → flip the existing row back
on), so the service can treat every distribute as idempotent.

Like ``knowledge_category.py``, this is a pure data-access layer: the role /
scope authorization (who may distribute to whom) lives in ``KnowledgeService``,
never here (AGENTS.md 铁律 #1: Controller→Service→Repository→Model, never
reversed).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_distribution import KnowledgeDistribution
from app.repositories.base import BaseRepository


class KnowledgeDistributionRepository(BaseRepository[KnowledgeDistribution]):
    """Reference-model link CRUD + source/target listings."""

    model = KnowledgeDistribution

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def get(self, dist_id: str) -> KnowledgeDistribution | None:
        """A distribution row by id (regardless of is_active — audit rows included).

        ``revoke_distribution`` uses this to find the row to flip; it must NOT
        silently miss a revoked row, so unlike ``list_for_target`` it does not
        filter on ``is_active``.
        """
        stmt = select(KnowledgeDistribution).where(
            KnowledgeDistribution.id == dist_id
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def find_for_pair(
        self, source_doc_id: str, target_tenant_id: str
    ) -> KnowledgeDistribution | None:
        """The (doc, target) row if one exists (regardless of is_active).

        ``UniqueConstraint(source_doc_id, target_tenant_id)`` guarantees at most
        one such row; this lookup is the upsert's pre-check so ``create`` never
        relies on catching IntegrityError (which behaves differently across
        SQLite/PG flush timing and forces a session rollback that loses pending
        work). A plain pre-check is deterministic and backend-agnostic.
        """
        stmt = select(KnowledgeDistribution).where(
            KnowledgeDistribution.source_doc_id == source_doc_id,
            KnowledgeDistribution.target_tenant_id == target_tenant_id,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def create(
        self,
        *,
        source_doc_id: str,
        target_tenant_id: str,
        distributed_by: str | None,
    ) -> KnowledgeDistribution:
        """Idempotent upsert of one (doc, target) distribution row.

        Re-distributing an already-distributed doc re-enables the existing row
        (Feature B upsert): if a ``(source_doc_id, target_tenant_id)`` row already
        exists (maybe revoked), flip its ``is_active`` back to True and refresh
        ``distributed_by`` to the new pusher; otherwise insert a new active row.
        Either way the returned row is active and reflects this push.

        Implemented as a pre-check (``find_for_pair``) rather than catching
        IntegrityError because the exception's flush timing differs across SQLite
        and Postgres, and a rollback to recover would discard the caller's other
        pending writes. The ``UniqueConstraint`` remains the hard guard against
        races (two concurrent creates still cannot produce two rows).
        """
        existing = await self.find_for_pair(source_doc_id, target_tenant_id)
        if existing is not None:
            existing.is_active = True
            existing.distributed_by = distributed_by
            await self.db.flush()
            return existing
        row = KnowledgeDistribution(
            source_doc_id=source_doc_id,
            target_tenant_id=target_tenant_id,
            distributed_by=distributed_by,
            is_active=True,
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def deactivate(self, dist_id: str) -> bool:
        """Soft-revoke: flip ``is_active`` to False (D4). Returns whether a row
        was actually flipped.

        The row is preserved (not deleted) so the audit trail of who-pushed-what-
        when stays intact. ``False`` means the id did not match any row.
        """
        row = await self.get(dist_id)
        if row is None:
            return False
        row.is_active = False
        await self.db.flush()
        return True

    async def list_for_source(
        self, source_doc_id: str, *, active_only: bool = False
    ) -> list[KnowledgeDistribution]:
        """All distribution rows originating from a document.

        An admin following a doc's distribution footprint wants revoked rows too
        (audit), so ``active_only`` defaults False. Pass True to see only the
        currently-effective pushes.
        """
        stmt = select(KnowledgeDistribution).where(
            KnowledgeDistribution.source_doc_id == source_doc_id
        )
        if active_only:
            stmt = stmt.where(KnowledgeDistribution.is_active.is_(True))
        stmt = stmt.order_by(KnowledgeDistribution.distributed_at.desc())
        return list((await self.db.execute(stmt)).scalars().all())

    async def list_for_target(
        self, target_tenant_id: str
    ) -> list[KnowledgeDistribution]:
        """Active distributions pushed TO a store — the store's "what was
        distributed to me" view.

        Revoked rows are excluded: a store's list/retrieve must never surface a
        revoked document (the same ``is_active=True`` predicate
        ``list_visible_for`` uses). Audit of revoked pushes is the source-side
        view (``list_for_source``).
        """
        stmt = (
            select(KnowledgeDistribution)
            .where(
                KnowledgeDistribution.target_tenant_id == target_tenant_id,
                KnowledgeDistribution.is_active.is_(True),
            )
            .order_by(KnowledgeDistribution.distributed_at.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())
