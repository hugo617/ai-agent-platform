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

    async def list(self, user_id: str, tenant_id: str) -> list[OrganizationRead]:
        await permission_service.require(user_id, tenant_id, self.OBJECT, "read")
        rows = await self.repo.list_for_tenant(tenant_id)
        return [OrganizationRead.model_validate(r) for r in rows]

    async def tree(self, user_id: str, tenant_id: str) -> list[OrganizationTreeNode]:
        await permission_service.require(user_id, tenant_id, self.OBJECT, "read")
        rows = await self.repo.list_for_tenant(tenant_id)
        return _build_tree(rows)

    async def create(
        self, actor_id: str, tenant_id: str, payload: OrganizationCreate
    ) -> OrganizationRead:
        await permission_service.require(actor_id, tenant_id, self.OBJECT, "create")
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
        self, actor_id: str, tenant_id: str, org_id: str, payload: OrganizationUpdate
    ) -> OrganizationRead:
        await permission_service.require(actor_id, tenant_id, self.OBJECT, "update")
        org = await self.repo.get_for_tenant(tenant_id, org_id)
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
                parent = await self.repo.get_for_tenant(tenant_id, payload.parent_id)
                if parent is None:
                    raise ValueError(
                        f"parent organization {payload.parent_id} not found"
                    )
                org.path = _compute_path(parent.path, parent.id)
            else:
                org.path = None
            org.parent_id = payload.parent_id or None
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
        self, actor_id: str, tenant_id: str, org_id: str
    ) -> None:
        await permission_service.require(actor_id, tenant_id, self.OBJECT, "delete")
        org = await self.repo.get_for_tenant(tenant_id, org_id)
        if org is None:
            raise ValueError(f"organization {org_id} not found")
        # Reparent direct children to this org's parent and recompute their path
        # so the lineage stays consistent (avoids stale ancestor chains).
        grandparent_path: str | None = None
        if org.parent_id:
            grandparent = await self.repo.get_for_tenant(tenant_id, org.parent_id)
            grandparent_path = grandparent.path if grandparent else None
        children = [
            o for o in await self.repo.list_for_tenant(tenant_id)
            if o.parent_id == org_id
        ]
        for c in children:
            c.parent_id = org.parent_id
            c.path = _compute_path(grandparent_path, org.parent_id)
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
