"""Role management service.

Roles are the admin-facing record of "what groups of permissions exist in this
tenant". The actual enforcement still happens in casbin (the seeded role names
owner/admin/member are what casbin's grouping policy references), but admins
use this CRUD to create custom display roles. The three system roles are seeded
when a tenant is created (see ``tenant_service``) and protected from deletion.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rbac import Role
from app.repositories.rbac import RolePermissionRepository, RoleRepository
from app.schemas.rbac import (
    RoleCreate,
    RoleLabel,
    RolePermissionGrant,
    RolePermissionRead,
    RoleRead,
    RoleUpdate,
)
from app.services.errors import BizError, NotFoundError
from app.services.logging_service import LoggingService
from app.services.permission_service import permission_service


class RbacService:
    OBJECT = "roles"

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.roles = RoleRepository(db)
        self.role_perms = RolePermissionRepository(db)
        self.logs = LoggingService(db)

    async def list(
        self,
        user_id: str,
        tenant_id: str,
        platform_role: str | None = None,
    ) -> list[RoleRead]:
        await permission_service.require(
            user_id, tenant_id, self.OBJECT, "read", platform_role=platform_role
        )
        rows = await self.roles.list_for_tenant(tenant_id)
        return [RoleRead.model_validate(r) for r in rows]

    async def labels(
        self,
        user_id: str,
        tenant_id: str,
        platform_role: str | None = None,
    ) -> list[RoleLabel]:
        await permission_service.require(
            user_id, tenant_id, self.OBJECT, "read", platform_role=platform_role
        )
        rows = await self.roles.list_for_tenant(tenant_id)
        return [RoleLabel(id=r.id, name=r.name, code=r.code) for r in rows]

    async def create(
        self,
        actor_id: str,
        tenant_id: str,
        payload: RoleCreate,
        platform_role: str | None = None,
    ) -> RoleRead:
        await permission_service.require(
            actor_id, tenant_id, self.OBJECT, "create", platform_role=platform_role
        )
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
            raise BizError("role code or name already exists in this tenant") from e

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
        self,
        actor_id: str,
        tenant_id: str,
        role_id: str,
        payload: RoleUpdate,
        platform_role: str | None = None,
    ) -> RoleRead:
        await permission_service.require(
            actor_id, tenant_id, self.OBJECT, "update", platform_role=platform_role
        )
        role = await self.roles.get_for_tenant(tenant_id, role_id)
        if role is None:
            raise NotFoundError(f"role {role_id} not found")
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

    async def delete(
        self,
        actor_id: str,
        tenant_id: str,
        role_id: str,
        platform_role: str | None = None,
    ) -> None:
        await permission_service.require(
            actor_id, tenant_id, self.OBJECT, "delete", platform_role=platform_role
        )
        role = await self.roles.get_for_tenant(tenant_id, role_id)
        if role is None:
            raise NotFoundError(f"role {role_id} not found")
        if role.is_system:
            raise BizError("system roles cannot be deleted")
        role.is_deleted = True
        role.deleted_at = datetime.now(UTC)
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

    # ----------------------------------------------- role ↔ permission grants

    async def _require_role(self, tenant_id: str, role_id: str) -> Role:
        role = await self.roles.get_for_tenant(tenant_id, role_id)
        if role is None:
            raise NotFoundError(f"role {role_id} not found")
        return role

    async def list_permissions(
        self,
        actor_id: str,
        tenant_id: str,
        role_id: str,
        platform_role: str | None = None,
    ) -> list[RolePermissionRead]:
        """Active ``(obj, act)`` grants for a role (current SCD2 state)."""
        await permission_service.require(
            actor_id, tenant_id, self.OBJECT, "read", platform_role=platform_role
        )
        await self._require_role(tenant_id, role_id)
        active = await self.role_perms.current_permissions(role_id, tenant_id)
        out: list[RolePermissionRead] = []
        for row in active:
            obj, act = await permission_service._permission_obj_act(
                self.db, row.permission_id
            )
            out.append(
                RolePermissionRead(
                    id=row.id,
                    role_id=row.role_id,
                    permission_id=row.permission_id,
                    obj=obj,
                    act=act,
                    valid_from=row.valid_from,
                    valid_to=row.valid_to,
                )
            )
        return out

    async def grant_permission(
        self,
        actor_id: str,
        tenant_id: str,
        role_id: str,
        payload: RolePermissionGrant,
        platform_role: str | None = None,
    ) -> RolePermissionRead:
        """Grant ``(obj, act)`` to a role: write SCD2 + resync casbin + audit.

        Constitution write path: SCD2 current row → casbin sync → system_logs.
        """
        await permission_service.require(
            actor_id, tenant_id, self.OBJECT, "update", platform_role=platform_role
        )
        role = await self._require_role(tenant_id, role_id)

        pid = await permission_service._upsert_permission(
            self.db, tenant_id, payload.obj, payload.act
        )
        await self.role_perms.grant(role.id, pid, tenant_id)
        await permission_service.sync_role_permissions_to_casbin(
            self.db, role.id, tenant_id
        )
        await self.logs.record(
            action="role.grant",
            module="roles",
            message=f"granted {payload.obj}:{payload.act} to role {role.code}",
            user_id=actor_id,
            tenant_id=tenant_id,
            resource_type="role",
            resource_id=role.id,
            new_values={"obj": payload.obj, "act": payload.act},
        )
        await self.db.commit()
        # Return the now-current row (re-read so valid_from is server-set).
        active = await self.role_perms.current_permissions(role.id, tenant_id)
        row = next((r for r in active if r.permission_id == pid), None)
        return RolePermissionRead(
            id=row.id,
            role_id=row.role_id,
            permission_id=row.permission_id,
            obj=payload.obj,
            act=payload.act,
            valid_from=row.valid_from,
            valid_to=row.valid_to,
        )

    async def revoke_permission(
        self,
        actor_id: str,
        tenant_id: str,
        role_id: str,
        permission_id: str,
        platform_role: str | None = None,
    ) -> None:
        """Revoke a permission from a role: close SCD2 row + resync casbin + audit."""
        await permission_service.require(
            actor_id, tenant_id, self.OBJECT, "update", platform_role=platform_role
        )
        role = await self._require_role(tenant_id, role_id)
        obj, act = await permission_service._permission_obj_act(
            self.db, permission_id
        )
        removed = await self.role_perms.revoke(role.id, permission_id, tenant_id)
        if not removed:
            raise NotFoundError("permission is not currently granted to this role")
        await permission_service.sync_role_permissions_to_casbin(
            self.db, role.id, tenant_id
        )
        await self.logs.record(
            action="role.revoke",
            module="roles",
            message=f"revoked {obj}:{act} from role {role.code}",
            user_id=actor_id,
            tenant_id=tenant_id,
            resource_type="role",
            resource_id=role.id,
            old_values={"obj": obj, "act": act},
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
