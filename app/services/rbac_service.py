"""Role management service.

Roles are the admin-facing record of "what groups of permissions exist in this
tenant". The actual enforcement still happens in casbin (the seeded role names
owner/admin/member are what casbin's grouping policy references), but admins
use this CRUD to create custom display roles. The three system roles are seeded
when a tenant is created (see ``tenant_service``) and protected from deletion.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rbac import Role
from app.repositories.rbac import RoleRepository
from app.schemas.rbac import RoleCreate, RoleLabel, RoleRead, RoleUpdate
from app.services.logging_service import LoggingService
from app.services.permission_service import permission_service


class RbacService:
    OBJECT = "roles"

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.roles = RoleRepository(db)
        self.logs = LoggingService(db)

    async def list(self, user_id: str, tenant_id: str) -> list[RoleRead]:
        await permission_service.require(user_id, tenant_id, self.OBJECT, "read")
        rows = await self.roles.list_for_tenant(tenant_id)
        return [RoleRead.model_validate(r) for r in rows]

    async def labels(self, user_id: str, tenant_id: str) -> list[RoleLabel]:
        await permission_service.require(user_id, tenant_id, self.OBJECT, "read")
        rows = await self.roles.list_for_tenant(tenant_id)
        return [RoleLabel(id=r.id, name=r.name, code=r.code) for r in rows]

    async def create(
        self, actor_id: str, tenant_id: str, payload: RoleCreate
    ) -> RoleRead:
        await permission_service.require(actor_id, tenant_id, self.OBJECT, "create")
        role = Role(
            tenant_id=tenant_id,
            name=payload.name,
            code=payload.code,
            description=payload.description,
            sort_order=payload.sort_order,
            created_by=actor_id,
            updated_by=actor_id,
        )
        try:
            await self.roles.add(role)
        except IntegrityError as e:
            await self.db.rollback()
            raise ValueError("role code or name already exists in this tenant") from e

        await self.logs.record(
            action="role.create",
            module="roles",
            message=f"created role {role.code}",
            user_id=actor_id,
            tenant_id=tenant_id,
            resource_type="role",
            resource_id=role.id,
        )
        await self.db.commit()
        return RoleRead.model_validate(role)

    async def update(
        self, actor_id: str, tenant_id: str, role_id: str, payload: RoleUpdate
    ) -> RoleRead:
        await permission_service.require(actor_id, tenant_id, self.OBJECT, "update")
        role = await self.roles.get_for_tenant(tenant_id, role_id)
        if role is None:
            raise ValueError(f"role {role_id} not found")
        for field in ("name", "description", "sort_order", "status"):
            v = getattr(payload, field)
            if v is not None:
                setattr(role, field, v)
        role.updated_by = actor_id
        await self.logs.record(
            action="role.update",
            module="roles",
            message=f"updated role {role.code}",
            user_id=actor_id,
            tenant_id=tenant_id,
            resource_type="role",
            resource_id=role.id,
        )
        await self.db.commit()
        return RoleRead.model_validate(role)

    async def delete(self, actor_id: str, tenant_id: str, role_id: str) -> None:
        await permission_service.require(actor_id, tenant_id, self.OBJECT, "delete")
        role = await self.roles.get_for_tenant(tenant_id, role_id)
        if role is None:
            raise ValueError(f"role {role_id} not found")
        if role.is_system:
            raise ValueError("system roles cannot be deleted")
        role.is_deleted = True
        role.deleted_at = datetime.utcnow()
        await self.logs.record(
            action="role.delete",
            module="roles",
            message=f"deleted role {role.code}",
            user_id=actor_id,
            tenant_id=tenant_id,
            resource_type="role",
            resource_id=role.id,
            level="warn",
        )
        await self.db.commit()

    # ----------------------------------------------------------- seed helper

    async def seed_defaults(self, tenant_id: str) -> list[Role]:
        """Create the owner/admin/member system roles (idempotent).

        Called by ``tenant_service.create_tenant``. The role ``code`` matches
        the casbin role name so the user-management UI's role dropdown stays in
        sync with the enforcer.
        """
        defaults = [
            ("owner", "Owner", "全部权限"),
            ("admin", "Admin", "管理权限（不含计费/删除）"),
            ("member", "Member", "只读 + 对话"),
        ]
        created: list[Role] = []
        for idx, (code, name, desc) in enumerate(defaults):
            existing = await self.roles.get_by_code(tenant_id, code)
            if existing is not None:
                continue
            role = Role(
                tenant_id=tenant_id,
                name=name,
                code=code,
                description=desc,
                is_system=True,
                sort_order=idx,
            )
            self.db.add(role)
            created.append(role)
        if created:
            await self.db.flush()
        return created
