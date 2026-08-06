"""ORM model for ``knowledge_categories`` (knowledge-tiered foundation).

A Category is a topic grouping for knowledge documents (e.g. 产品手册 / FAQ /
话术脚本 / 服务规范 / 促销文案). Categories are themselves tiered by ``scope``:

  - ``platform`` — platform-wide, pre-seeded by the migration and creatable by
    super_admin. ``group_id`` and ``tenant_id`` are NULL.
  - ``group``    — a chain/group defines its own Category. Carries ``group_id``
    (the Group it belongs to), ``tenant_id`` NULL.
  - ``store``    — a single store's own Category. Carries ``tenant_id`` (the
    store), ``group_id`` NULL.

Lower tiers list higher-tier Categories (a store sees platform + its group +
its own). Soft-deleted via ``is_deleted`` + a partial unique index so a deleted
Category's name can be reused within the same scope (mirrors User/Group).

Dual-DB: all columns are scalars (String/Integer/Boolean), and the partial
unique index is mirrored across PG (``postgresql_where``) and SQLite
(``sqlite_where``) so ``Base.metadata.create_all`` and the alembic migration
produce identical schemas on both.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class KnowledgeCategory(Base):
    """A tiered topic grouping for knowledge documents.

    See module docstring for the scope model. The migration seeds 5 platform
    Categories; Feature B adds the CRUD API that lets each tier create its own.
    """

    __tablename__ = "knowledge_categories"
    __table_args__ = (
        # Scope index: most queries filter by scope first (list visible = this
        # scope's rows), so scope is the primary access path.
        Index("ix_knowledge_categories_scope", "scope"),
        # Partial unique index: at most one *live* Category per
        # (scope, name, group_id, tenant_id). Soft-deleted rows keep their name
        # but are exempt, so a name can be reused after deletion. Mirrored
        # PG/SQLite (see Group.uq_groups_code_active / User.uq_users_username).
        Index(
            "uq_knowledge_categories_scope_name_active",
            "scope",
            "name",
            "group_id",
            "tenant_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # 'platform' | 'group' | 'store'. NOT NULL — every Category belongs to a
    # tier. The migration's seeded rows are scope='platform'.
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    # Set when scope='group' (the Group this Category belongs to). Nullable for
    # platform scope; NULL for store scope (store uses tenant_id). ondelete SET
    # NULL so deleting a group doesn't cascade-kill its Categories — platform /
    # store Categories survive and group Categories orphan softly (Feature B
    # decides whether to re-parent or surface them).
    group_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("groups.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Set when scope='store' (the store tenant). NULL for platform/group scope.
    # ondelete CASCADE: a deleted store takes its store Categories with it.
    tenant_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<KnowledgeCategory {self.id} {self.name} scope={self.scope}>"
        )
