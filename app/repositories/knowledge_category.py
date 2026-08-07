"""Repository for ``knowledge_categories`` (knowledge-tiered Feature B).

Categories are tiered by ``scope`` (platform / group / store). Reads go through
``list_visible``, which resolves the three-tier visibility rule per the caller's
role context — the WHERE clauses live here (not in the service) so the
multi-tenant/group isolation is enforced at the data-access layer, never
relying on a service "remembering" to filter.

Visibility matrix (plan slice 01 AC2):

- cross-tenant viewer (super_admin / hq_staff) → all live rows.
- group_admin → platform + own group + ALL sibling stores in that group
  (aggregated chain view).
- store owner/admin/member → platform + own group + own store only.

The ``is_cross_tenant_viewer`` predicate is computed by the SERVICE (it lives
in ``permission_service``, which the Repository layer must NOT import — AGENTS.md
铁律 #1: dependency direction Controller→Service→Repository→Model, never
reversed). The service passes the resulting bool down as
``include_all_tenants`` so this repo stays a pure data-access layer.

Writes (create/update/delete) carry the scope ownership columns verbatim; the
role↔scope authorization happens in ``KnowledgeCategoryService`` (G6), not here.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.group import GroupTenant
from app.models.knowledge_category import KnowledgeCategory
from app.repositories.base import BaseRepository


class KnowledgeCategoryRepository(BaseRepository[KnowledgeCategory]):
    """Tiered Category CRUD + three-path visibility reads."""

    model = KnowledgeCategory

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def get(self, category_id: str) -> KnowledgeCategory | None:
        """A *live* Category by id (filters out soft-deleted)."""
        stmt = select(KnowledgeCategory).where(
            KnowledgeCategory.id == category_id,
            KnowledgeCategory.is_deleted.is_(False),
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list_visible(
        self,
        *,
        tenant_id: str,
        group_id: str | None,
        include_all_tenants: bool,
        is_group_admin: bool,
    ) -> list[KnowledgeCategory]:
        """Live Categories visible to the caller, per the three-tier rule.

        ``tenant_id`` is the caller's home store; ``group_id`` is that store's
        group (None if the store belongs to no group — then only platform + own
        store Categories are visible, no group tier). ``include_all_tenants`` is
        the pre-computed ``is_cross_tenant_viewer(platform_role)`` result (handed
        down by the service so this repo doesn't import the service layer — 铁律
        #1). ``is_group_admin`` enables the aggregated chain view (sees sibling
        stores). Ordering is scope then sort_order then name for stable display.
        """
        base = select(KnowledgeCategory).where(KnowledgeCategory.is_deleted.is_(False))

        if include_all_tenants:
            # super_admin / hq_staff: every live Category, no tier filter.
            stmt = base
        elif is_group_admin and group_id is not None:
            # group_admin aggregated view: platform + own group + ALL sibling
            # stores in the group. Sibling store ids come from the group_tenants
            # reverse lookup; subquery keeps it one round-trip.
            sibling_store_ids = select(GroupTenant.tenant_id).where(
                GroupTenant.group_id == group_id
            )
            stmt = base.where(
                or_(
                    KnowledgeCategory.scope == "platform",
                    KnowledgeCategory.group_id == group_id,
                    # store-tier Categories of ANY store in this group.
                    KnowledgeCategory.tenant_id.in_(sibling_store_ids),
                )
            )
        else:
            # store view: platform + own group (if any) + own store only.
            clauses = [
                KnowledgeCategory.scope == "platform",
                KnowledgeCategory.tenant_id == tenant_id,
            ]
            if group_id is not None:
                clauses.append(KnowledgeCategory.group_id == group_id)
            stmt = base.where(or_(*clauses))

        stmt = stmt.order_by(
            KnowledgeCategory.scope,
            KnowledgeCategory.sort_order,
            KnowledgeCategory.name,
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def find_active_in_scope(
        self,
        *,
        scope: str,
        name: str,
        group_id: str | None = None,
        tenant_id: str | None = None,
    ) -> KnowledgeCategory | None:
        """A live Category matching (scope, name, group_id, tenant_id).

        Used by the service to surface a friendly BizError on duplicate before
        the partial unique index raises IntegrityError (the index is the real
        guard; this is the UX-layer pre-check).
        """
        stmt = select(KnowledgeCategory).where(
            KnowledgeCategory.scope == scope,
            KnowledgeCategory.name == name,
            KnowledgeCategory.is_deleted.is_(False),
        )
        if scope == "group":
            stmt = stmt.where(KnowledgeCategory.group_id == group_id)
        elif scope == "store":
            stmt = stmt.where(KnowledgeCategory.tenant_id == tenant_id)
        else:  # platform — both NULL
            stmt = stmt.where(KnowledgeCategory.group_id.is_(None))
        return (await self.db.execute(stmt)).scalar_one_or_none()
