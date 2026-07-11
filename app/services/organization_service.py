"""Organization tree service.

Orgs form a tenant-scoped hierarchy. The ``path`` column is a convenience for
ancestry queries but is kept simple (``/parent/child``); the tree is rebuilt in
memory for the API response by grouping on ``parent_id``.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.repositories.organization import OrganizationRepository
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationRead,
    OrganizationTreeNode,
    OrganizationUpdate,
)
from app.services.logging_service import LoggingService
from app.services.permission_service import permission_service


class OrganizationService:
    OBJECT = "organizations"

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = OrganizationRepository(db)
        self.logs = LoggingService(db)

    async def list(
        self,
        user_id: str,
        tenant_id: str,
        platform_role: str | None = None,
    ) -> list[OrganizationRead]:
        await permission_service.require(
            user_id, tenant_id, self.OBJECT, "read", platform_role=platform_role
        )
        rows = await self.repo.list_for_tenant(tenant_id)
        return [OrganizationRead.model_validate(r) for r in rows]

    async def tree(
        self,
        user_id: str,
        tenant_id: str,
        platform_role: str | None = None,
    ) -> list[OrganizationTreeNode]:
        await permission_service.require(
            user_id, tenant_id, self.OBJECT, "read", platform_role=platform_role
        )
        rows = await self.repo.list_for_tenant(tenant_id)
        return _build_tree(rows)

    async def create(
        self,
        actor_id: str,
        tenant_id: str,
        payload: OrganizationCreate,
        platform_role: str | None = None,
    ) -> OrganizationRead:
        await permission_service.require(
            actor_id, tenant_id, self.OBJECT, "create", platform_role=platform_role
        )
        path = None
        if payload.parent_id:
            parent = await self.repo.get_for_tenant(tenant_id, payload.parent_id)
            if parent is None:
                raise ValueError(f"parent organization {payload.parent_id} not found")
            path = _compute_path(parent.path, parent.id)
        org = Organization(
            tenant_id=tenant_id,
            name=payload.name,
            code=payload.code,
            parent_id=payload.parent_id,
            leader_id=payload.leader_id,
            sort_order=payload.sort_order,
            path=path,
        )
        await self.repo.add(org)
        await self.logs.record(
            action="organization.create",
            module="organizations",
            message=f"created organization {org.name}",
            user_id=actor_id,
            tenant_id=tenant_id,
            resource_type="organization",
            resource_id=org.id,
        )
        await self.db.commit()
        return OrganizationRead.model_validate(org)

    async def update(
        self,
        actor_id: str,
        tenant_id: str,
        org_id: str,
        payload: OrganizationUpdate,
        platform_role: str | None = None,
    ) -> OrganizationRead:
        await permission_service.require(
            user_id=actor_id,
            tenant_id=tenant_id,
            obj=self.OBJECT,
            act="update",
            platform_role=platform_role,
        )
        all_orgs = await self.repo.list_for_tenant(tenant_id)
        by_id = {o.id: o for o in all_orgs}
        org = by_id.get(org_id)
        if org is None:
            raise ValueError(f"organization {org_id} not found")
        for field in ("name", "code", "leader_id", "status", "sort_order"):
            v = getattr(payload, field)
            if v is not None:
                setattr(org, field, v)
        if payload.parent_id is not None and payload.parent_id != org.parent_id:
            if payload.parent_id == org.id:
                raise ValueError("an organization cannot be its own parent")
            if payload.parent_id:
                # Reject cycles: the new parent must not be a descendant of org.
                if _is_descendant(org_id, payload.parent_id, by_id):
                    raise ValueError(
                        "cannot move an organization beneath its own descendant"
                    )
                parent = by_id.get(payload.parent_id)
                if parent is None:
                    raise ValueError(
                        f"parent organization {payload.parent_id} not found"
                    )
            else:
                parent = None
            org.parent_id = payload.parent_id or None
            # Update the moved node's own path from its new parent, then
            # cascade the new path to its entire subtree.
            org.path = _compute_path(parent.path if parent else None, parent.id if parent else None)
            _recompute_subtree_paths(org, by_id)
        await self.logs.record(
            action="organization.update",
            module="organizations",
            message=f"updated organization {org.name}",
            user_id=actor_id,
            tenant_id=tenant_id,
            resource_type="organization",
            resource_id=org.id,
        )
        await self.db.commit()
        return OrganizationRead.model_validate(org)

    async def delete(
        self,
        actor_id: str,
        tenant_id: str,
        org_id: str,
        platform_role: str | None = None,
    ) -> None:
        await permission_service.require(
            user_id=actor_id,
            tenant_id=tenant_id,
            obj=self.OBJECT,
            act="delete",
            platform_role=platform_role,
        )
        all_orgs = await self.repo.list_for_tenant(tenant_id)
        by_id = {o.id: o for o in all_orgs}
        org = by_id.get(org_id)
        if org is None:
            raise ValueError(f"organization {org_id} not found")
        # Reparent direct children to this org's parent so the lineage stays
        # consistent, then recompute their subtree paths.
        new_parent_id = org.parent_id
        grandparent = by_id.get(new_parent_id) if new_parent_id else None
        grandparent_path = grandparent.path if grandparent else None
        children = [o for o in all_orgs if o.parent_id == org_id]
        for c in children:
            c.parent_id = new_parent_id
            c.path = _compute_path(grandparent_path, new_parent_id)
            # Cascade the new path to the reparented child's own descendants.
            _recompute_subtree_paths(c, by_id)
        await self.repo.delete(org)
        await self.logs.record(
            action="organization.delete",
            module="organizations",
            message=f"deleted organization {org.name}",
            user_id=actor_id,
            tenant_id=tenant_id,
            resource_type="organization",
            resource_id=org.id,
            level="warn",
        )
        await self.db.commit()


def _build_tree(rows: list[Organization]) -> list[OrganizationTreeNode]:
    """Assemble a flat list into a parent→children tree (roots first)."""
    nodes: dict[str, OrganizationTreeNode] = {
        r.id: OrganizationTreeNode.model_validate(r) for r in rows
    }
    roots: list[OrganizationTreeNode] = []
    for r in rows:
        node = nodes[r.id]
        if r.parent_id and r.parent_id in nodes:
            nodes[r.parent_id].children.append(node)
        else:
            roots.append(node)
    return roots


def _compute_path(parent_path: str | None, parent_id: str | None) -> str | None:
    """Materialised path for a node whose parent has ``parent_path``.

    Root nodes (``parent_id is None``) have ``path = None``. Children append
    their parent's id: a child of ``/a/b`` becomes ``/a/b/<parent_id>``.
    """
    if not parent_id:
        return None
    prefix = parent_path or ""
    return f"{prefix}/{parent_id}"


def _is_descendant(
    ancestor_id: str, candidate_id: str, by_id: dict[str, Organization]
) -> bool:
    """True if ``candidate_id`` is ``ancestor_id`` or sits beneath it.

    Used to reject reparenting a node under one of its own descendants (which
    would create a cycle). Walks parent links upward from the candidate.
    """
    cur = candidate_id
    seen: set[str] = set()
    while cur is not None and cur not in seen:
        if cur == ancestor_id:
            return True
        seen.add(cur)
        node = by_id.get(cur)
        cur = node.parent_id if node is not None else None
    return False


def _recompute_subtree_paths(
    root: Organization, by_id: dict[str, Organization]
) -> None:
    """Recompute ``path`` for ``root`` and all of its descendants.

    A node's path is built from its parent's path + the parent's id. We walk
    down from ``root`` breadth-first so each child reads its (already-updated)
    parent path. ``root``'s own path is assumed already correct.
    """
    frontier = [root]
    while frontier:
        parent = frontier.pop()
        for o in by_id.values():
            if o.parent_id == parent.id:
                o.path = _compute_path(parent.path, parent.id)
                frontier.append(o)
