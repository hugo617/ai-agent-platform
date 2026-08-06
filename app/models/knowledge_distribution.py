"""ORM model for ``knowledge_distribution`` (knowledge-tiered foundation).

A distribution row is the **reference-model** link between a source document
and a target store: "doc X is visible to store Y". It points at the source
document and its chunks — it does **not** copy them (knowledge-tiered D4). This
keeps distribution instant and keeps edits to the source immediately visible
downstream; revoking a distribution is a soft flip (``is_active = false``) that
preserves the audit trail rather than a hard delete.

Columns:

  - ``source_doc_id``   — FK documents, CASCADE (a hard-deleted source takes its
                          distributions with it; Feature B soft-deletes sources
                          and filters via is_active, see plan §10).
  - ``target_tenant_id``— FK tenants, CASCADE (the store the doc is pushed to).
  - ``distributed_by``  — FK users, SET NULL (who pushed it; the row survives
                          the user being deleted so the audit stays intact).
  - ``distributed_at``  — when it was pushed (audit timestamp).
  - ``is_active``       — True = in effect, False = revoked (D4 soft revoke).

``UniqueConstraint(source_doc_id, target_tenant_id)`` enforces "at most one row
per (doc, target)": re-distributing an already-distributed doc must re-enable
the existing row (Feature B's upsert), not insert a duplicate. ``is_active`` is
deliberately *outside* the unique key so the (doc, target) relationship has a
single lifecycle row that flips on/off.

Dual-DB: pure scalar columns, mirrored across PG and SQLite.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class KnowledgeDistribution(Base):
    """A reference-model link pushing a source document to a target store.

    See module docstring for the reference model (D4) and the revoke semantics.
    """

    __tablename__ = "knowledge_distribution"
    __table_args__ = (
        # One row per (doc, target) — see module docstring. Re-distributing an
        # already-distributed doc re-enables the existing row (Feature B upsert).
        UniqueConstraint(
            "source_doc_id", "target_tenant_id", name="uq_knowledge_distribution"
        ),
        # A store's "what was distributed to me" query filters by target — this
        # index backs it (Feature B's list/retrieve path).
        Index("ix_knowledge_distribution_target_tenant_id", "target_tenant_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    source_doc_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_tenant_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    distributed_by: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    distributed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # D4: revoke = soft flip (is_active=false), not a hard delete. Preserves the
    # audit trail of who-pushed-what-when. DEFAULT True via both Python default
    # and server_default so INSERT and migration backfill agree.
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )

    def __repr__(self) -> str:
        return (
            f"<KnowledgeDistribution doc={self.source_doc_id} "
            f"target={self.target_tenant_id} active={self.is_active}>"
        )
