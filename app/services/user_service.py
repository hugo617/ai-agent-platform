"""User management service — full CRUD with bcrypt, casbin sync, and audit log.

Each mutation:
  1. checks the actor has the matching ``users:*`` permission (casbin),
  2. keeps the DB ``user_tenants`` role + casbin grouping policy in sync,
  3. records a SystemLog audit entry (best-effort).

Tenant scoping: every read is filtered to the caller's tenant via
``UserListRepository`` (which joins ``user_tenants``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.password import hash_password
from app.models.organization import Organization
from app.models.rbac import Role
from app.models.tenant import User
from app.repositories.security import LoginMethodRepository, SessionRepository
from app.repositories.tenant import UserRepository, UserTenantRepository
from app.repositories.user import (
    UserFilters,
    UserListRepository,
    serialize_user,
)
from app.schemas.user import (
    VALID_STATUSES,
    PasswordReset,
    UserCreate,
    UserListResponse,
    UserRead,
    UserStatistics,
    UserUpdate,
)
from app.services.errors import BizError, NotFoundError
from app.services.logging_service import LoggingService
from app.services.permission_service import permission_service


class UserService:
    OBJECT = "users"

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.memberships = UserTenantRepository(db)
        self.list_repo = UserListRepository(db)
        self.login_methods = LoginMethodRepository(db)
        self.sessions = SessionRepository(db)
        self.logs = LoggingService(db)

    # ------------------------------------------------------------------ read

    async def list(
        self,
        actor_id: str,
        tenant_id: str,
        filters: UserFilters,
        platform_role: str | None = None,
    ) -> UserListResponse:
        is_super_admin = platform_role == "super_admin"
        if not is_super_admin:
            await permission_service.require(actor_id, tenant_id, self.OBJECT, "read")

        users, total = await self.list_repo.list(
            tenant_id, filters, super_admin=is_super_admin
        )
        if is_super_admin:
            tenant_info = await self.list_repo.batch_tenant_info([u.id for u in users])
            items = [await self._read_all(u, tenant_info) for u in users]
        else:
            items = [await self._read(tenant_id, u) for u in users]
        return UserListResponse(
            items=items,
            total=total,
            page=filters.page,
            limit=filters.limit,
            total_pages=(total + filters.limit - 1) // filters.limit,
        )

    async def get(
        self,
        actor_id: str,
        tenant_id: str,
        user_id: str,
        platform_role: str | None = None,
    ) -> UserRead:
        is_super_admin = platform_role == "super_admin"
        if not is_super_admin:
            await permission_service.require(actor_id, tenant_id, self.OBJECT, "read")

        if is_super_admin:
            user = await self.users.get(user_id)
            if user is None or user.is_deleted:
                raise NotFoundError(f"用户 {user_id} 不存在")
            tenant_info = await self.list_repo.batch_tenant_info([user_id])
            return await self._read_all(user, tenant_info)
        else:
            user = await self.list_repo.get(tenant_id, user_id)
            if user is None:
                raise NotFoundError(f"用户 {user_id} 不在该租户中")
            return await self._read(tenant_id, user)

    async def statistics(
        self,
        actor_id: str,
        tenant_id: str,
        platform_role: str | None = None,
    ) -> UserStatistics:
        is_super_admin = platform_role == "super_admin"
        if not is_super_admin:
            await permission_service.require(actor_id, tenant_id, self.OBJECT, "read")
        return UserStatistics(
            **await self.list_repo.statistics(tenant_id, super_admin=is_super_admin)
        )

    async def _read(self, tenant_id: str, user: User) -> UserRead:
        # Re-fetch via a fresh select so all columns (incl. server defaults like
        # created_at/updated_at) are loaded eagerly — avoids lazy-load IO on an
        # object whose session may have been expired by a commit.
        fresh = await self.list_repo.get(tenant_id, user.id)
        if fresh is not None:
            user = fresh
        membership = await self.memberships.get_membership(user.id, tenant_id)
        role = membership.role if membership else None
        role_brief = None
        if role:
            r = await self._find_role(tenant_id, role)
            role_brief = {"id": r.id, "name": r.name, "code": r.code} if r else None
            if role_brief is None:
                role_brief = {"id": "", "name": role, "code": role}
        orgs = await self.list_repo.list_organizations(user.id)
        data = serialize_user(user, organizations=orgs)
        data["role"] = role_brief
        return UserRead.model_validate(data)

    async def _read_all(
        self, user: User, tenant_info: dict[str, tuple[str | None, str | None]]
    ) -> UserRead:
        """Read a user for super admin view, including their cross-tenant info."""
        # Re-fetch via a fresh select so all columns are loaded eagerly —
        # avoids lazy-load IO on an object whose session may have been expired
        # by a commit (Session.get() would return the stale identity-map row).
        fresh = (
            await self.db.execute(select(User).where(User.id == user.id))
        ).scalar_one_or_none()
        if fresh is not None:
            user = fresh
        tid, tname = tenant_info.get(user.id, (None, None))
        membership = await self.memberships.get_membership(user.id, tid) if tid else None
        role = membership.role if membership else None
        role_brief = None
        if role and tid:
            r = await self._find_role(tid, role)
            role_brief = {"id": r.id, "name": r.name, "code": r.code} if r else None
            if role_brief is None:
                role_brief = {"id": "", "name": role, "code": role}
        orgs = await self.list_repo.list_organizations(user.id)
        data = serialize_user(user, organizations=orgs)
        data["role"] = role_brief
        data["tenant_id"] = tid
        data["tenant_name"] = tname
        return UserRead.model_validate(data)

    async def _find_role(self, tenant_id: str, code: str) -> Role | None:
        stmt = select(Role).where(
            Role.tenant_id == tenant_id,
            Role.code == code,
            Role.is_deleted.is_(False),
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    # ----------------------------------------------------------------- create

    async def create(
        self, actor_id: str, tenant_id: str, payload: UserCreate
    ) -> UserRead:
        await permission_service.require(actor_id, tenant_id, self.OBJECT, "create")

        if payload.status not in VALID_STATUSES:
            raise BizError(f"无效的状态: {payload.status}")

        # Uniqueness checks (global on username/email — IDs are cross-tenant).
        if await self.users.get_by_username(payload.username):
            raise BizError("用户名已存在")
        if payload.email and await self.users.get_by_email(str(payload.email)):
            raise BizError("邮箱已存在")

        # Validate organization_ids belong to this tenant.
        await self._validate_org_ids(tenant_id, payload.organization_ids)

        user = User(
            id=uuid.uuid4().hex,
            username=payload.username,
            email=str(payload.email),
            password=hash_password(payload.password),
            display_name=payload.display_name,
            real_name=payload.real_name,
            phone=payload.phone,
            avatar=payload.avatar or "/avatars/default.jpg",
            status=payload.status,
            created_by=actor_id,
            updated_by=actor_id,
        )
        try:
            self.db.add(user)
            await self.db.flush()
        except IntegrityError as e:
            await self.db.rollback()
            raise BizError("用户名或邮箱已存在") from e

        # Tenant membership + casbin role (SCD2 write path).
        await self.memberships.assign_role(user.id, tenant_id, payload.role)
        await permission_service.add_role_for_user_in_domain(
            user.id, payload.role, tenant_id
        )

        # Org links.
        if payload.organization_ids:
            await self.list_repo.sync_organizations(user.id, payload.organization_ids)

        # Primary email login method.
        self.login_methods.add_local_email(user.id, str(payload.email))

        await self.logs.record(
            action="user.create",
            module="users",
            message=f"created user {user.username}",
            user_id=actor_id,
            tenant_id=tenant_id,
            level="info",
            resource_type="user",
            resource_id=user.id,
            new_values={"username": user.username, "email": user.email, "role": payload.role},
        )
        await self.db.commit()
        return await self._read(tenant_id, user)

    # ----------------------------------------------------------------- update

    async def update(
        self,
        actor_id: str,
        tenant_id: str,
        user_id: str,
        payload: UserUpdate,
        platform_role: str | None = None,
    ) -> UserRead:
        is_super_admin = platform_role == "super_admin"
        if not is_super_admin:
            await permission_service.require(actor_id, tenant_id, self.OBJECT, "update")

        # Super admin looks up globally (cross-tenant); tenant admins are scoped.
        if is_super_admin:
            user = await self.users.get(user_id)
            if user is None or user.is_deleted:
                raise NotFoundError(f"用户 {user_id} 不存在")
        else:
            user = await self.list_repo.get(tenant_id, user_id)
            if user is None:
                raise NotFoundError(f"用户 {user_id} 不在该租户中")

        old = _snapshot(user)
        changes: dict[str, Any] = {}

        if payload.username is not None and payload.username != user.username:
            if await self.users.get_by_username(payload.username):
                raise BizError("用户名已存在")
            user.username = payload.username
            changes["username"] = payload.username
        if payload.email is not None and str(payload.email) != user.email:
            if await self.users.get_by_email(str(payload.email)):
                raise BizError("邮箱已存在")
            user.email = str(payload.email)
            changes["email"] = str(payload.email)
        for field in ("display_name", "real_name", "phone", "avatar"):
            v = getattr(payload, field)
            if v is not None and v != getattr(user, field):
                setattr(user, field, v)
                changes[field] = v
        if payload.status is not None:
            if payload.status not in VALID_STATUSES:
                raise BizError(f"无效的状态: {payload.status}")
            if payload.status != user.status:
                user.status = payload.status
                changes["status"] = payload.status
        user.updated_by = actor_id

        # Role change (mirrored into casbin) — SCD2 write path.
        # Super admins operate cross-tenant: a tenant-scoped role change is
        # ambiguous (which tenant's membership?), so it is ignored here. Role
        # management for cross-tenant users should go through the members page.
        if payload.role is not None and not is_super_admin:
            membership = await self.memberships.current_role(user.id, tenant_id)
            if membership is None:
                raise NotFoundError(f"用户 {user_id} 不是该租户的成员")
            if membership.role != payload.role:
                old_role = membership.role
                await self.memberships.assign_role(
                    user.id, tenant_id, payload.role
                )
                changes["role"] = {"from": old_role, "to": payload.role}
                await permission_service.set_role_for_user_in_domain(
                    user.id, payload.role, tenant_id
                )

        # Org links (tenant-scoped — skipped for super admins editing across
        # tenants, since the org tree belongs to a specific tenant).
        if payload.organization_ids is not None and not is_super_admin:
            await self._validate_org_ids(tenant_id, payload.organization_ids)
            await self.list_repo.sync_organizations(user.id, payload.organization_ids)
            changes["organization_ids"] = payload.organization_ids

        await self.logs.record(
            action="user.update",
            module="users",
            message=f"updated user {user.username}",
            user_id=actor_id,
            tenant_id=tenant_id,
            level="info",
            resource_type="user",
            resource_id=user.id,
            old_values=old,
            new_values=changes or None,
        )
        await self.db.commit()
        if is_super_admin:
            tenant_info = await self.list_repo.batch_tenant_info([user.id])
            return await self._read_all(user, tenant_info)
        return await self._read(tenant_id, user)

    # ----------------------------------------------------------------- delete

    async def delete(
        self,
        actor_id: str,
        tenant_id: str,
        user_id: str,
        platform_role: str | None = None,
    ) -> None:
        is_super_admin = platform_role == "super_admin"
        if not is_super_admin:
            await permission_service.require(actor_id, tenant_id, self.OBJECT, "delete")
        if actor_id == user_id:
            raise BizError("不能删除自己")

        # Super admin soft-deletes the global User and tears down membership
        # across ALL tenants; a tenant admin only operates within their tenant.
        if is_super_admin:
            user = await self.users.get(user_id)
            if user is None or user.is_deleted:
                raise NotFoundError(f"用户 {user_id} 不存在")
            affected_tenants = [
                m.tenant_id for m in await self.memberships.list_for_user(user_id)
            ]
        else:
            user = await self.list_repo.get(tenant_id, user_id)
            if user is None:
                raise NotFoundError(f"用户 {user_id} 不在该租户中")
            affected_tenants = [tenant_id]

        old = _snapshot(user)
        user.is_deleted = True
        user.deleted_at = datetime.now(UTC)
        user.updated_by = actor_id
        # Close every active membership (SCD2) + strip casbin roles. Super
        # admins iterate all the user's tenants; tenant admins just their own.
        for tid in affected_tenants:
            await self.memberships.remove_member(user_id, tid)
            await permission_service.remove_user_from_tenant(user_id, tid)
        # Revoke every outstanding session so a deleted user's token stops
        # working immediately (get_current_user also rejects soft-deleted users).
        await self.sessions.deactivate_all_for_user(user_id)
        await self.logs.record(
            action="user.delete",
            module="users",
            message=f"deleted user {user.username}",
            user_id=actor_id,
            tenant_id=tenant_id,
            level="warn",
            resource_type="user",
            resource_id=user.id,
            old_values=old,
        )
        await self.db.commit()

    # ----------------------------------------------------- status / password

    async def change_status(
        self,
        actor_id: str,
        tenant_id: str,
        user_id: str,
        status: str,
        platform_role: str | None = None,
    ) -> UserRead:
        is_super_admin = platform_role == "super_admin"
        if not is_super_admin:
            await permission_service.require(actor_id, tenant_id, self.OBJECT, "update")
        if status not in VALID_STATUSES:
            raise BizError(f"无效的状态: {status}")
        if is_super_admin:
            user = await self.users.get(user_id)
            if user is None or user.is_deleted:
                raise NotFoundError(f"用户 {user_id} 不存在")
        else:
            user = await self.list_repo.get(tenant_id, user_id)
            if user is None:
                raise NotFoundError(f"用户 {user_id} 不在该租户中")
        old = user.status
        user.status = status
        user.updated_by = actor_id
        # Locking / disabling an account must kill its outstanding sessions —
        # otherwise the change has no effect until the token expires.
        if status != "active":
            await self.sessions.deactivate_all_for_user(user_id)
        await self.logs.record(
            action="user.status_change",
            module="users",
            message=f"user {user.username} status: {old} -> {status}",
            user_id=actor_id,
            tenant_id=tenant_id,
            level="warn",
            resource_type="user",
            resource_id=user.id,
            old_values={"status": old},
            new_values={"status": status},
        )
        await self.db.commit()
        if is_super_admin:
            tenant_info = await self.list_repo.batch_tenant_info([user.id])
            return await self._read_all(user, tenant_info)
        return await self._read(tenant_id, user)

    async def reset_password(
        self,
        actor_id: str,
        tenant_id: str,
        user_id: str,
        payload: PasswordReset,
        platform_role: str | None = None,
    ) -> None:
        is_super_admin = platform_role == "super_admin"
        if not is_super_admin:
            await permission_service.require(actor_id, tenant_id, self.OBJECT, "update")
        if is_super_admin:
            user = await self.users.get(user_id)
            if user is None or user.is_deleted:
                raise NotFoundError(f"用户 {user_id} 不存在")
        else:
            user = await self.list_repo.get(tenant_id, user_id)
            if user is None:
                raise NotFoundError(f"用户 {user_id} 不在该租户中")
        user.password = hash_password(payload.new_password)
        user.password_updated_at = datetime.now(UTC)
        user.updated_by = actor_id
        # Force re-authentication everywhere: drop all sessions so the new
        # password is the only way back in.
        await self.sessions.deactivate_all_for_user(user_id)
        await self.logs.record(
            action="user.reset_password",
            module="users",
            message=f"reset password for user {user.username}",
            user_id=actor_id,
            tenant_id=tenant_id,
            level="warn",
            resource_type="user",
            resource_id=user.id,
        )
        await self.db.commit()

    # --------------------------------------------------------------- helpers

    async def _validate_org_ids(self, tenant_id: str, org_ids: list[str]) -> None:
        if not org_ids:
            return
        stmt = select(Organization).where(
            Organization.tenant_id == tenant_id,
            Organization.id.in_(org_ids),
        )
        found = list((await self.db.execute(stmt)).scalars().all())
        missing = set(org_ids) - {o.id for o in found}
        if missing:
            raise BizError(f"未知的组织 ID: {sorted(missing)}")


def _snapshot(user: User) -> dict[str, Any]:
    return {
        "username": user.username,
        "email": user.email,
        "status": user.status,
        "real_name": user.real_name,
        "phone": user.phone,
    }
