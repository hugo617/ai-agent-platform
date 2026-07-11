"""Tenant membership service — CRUD over the user_tenants association.

Moved here from user_service when users.py became a full user-profile CRUD.
Memberships are about *who is in the tenant and with which role*; the user
profile (username/password/contact info) is managed through UserService.

Each operation checks the matching ``users:*`` casbin permission and keeps the
casbin grouping policy (``g``) in sync with the DB role.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import UserTenant
from app.repositories.tenant import UserRepository, UserTenantRepository
from app.schemas.user import MemberCreate, MemberRead, MemberUpdate
from app.services.permission_service import permission_service


class MemberService:
    OBJECT = "users"

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.memberships = UserTenantRepository(db)

    def _to_read(self, m: UserTenant) -> MemberRead:
        return MemberRead(
            user_id=m.user_id,
            role=m.role,
            email=m.user.email if m.user else None,
            display_name=m.user.display_name if m.user else None,
            joined_at=m.created_at,
        )

    async def list(
        self,
        user_id: str,
        tenant_id: str,
        platform_role: str | None = None,
    ) -> list[MemberRead]:
        await permission_service.require(
            user_id, tenant_id, self.OBJECT, "read", platform_role=platform_role
        )
        rows = await self.memberships.list_for_tenant(tenant_id)
        return [self._to_read(m) for m in rows]

    async def add(
        self,
        actor_id: str,
        tenant_id: str,
        payload: MemberCreate,
        platform_role: str | None = None,
    ) -> MemberRead:
        """Add a user (by id) to the current tenant with a given role."""
        await permission_service.require(
            actor_id, tenant_id, self.OBJECT, "create", platform_role=platform_role
        )

        user = await self.users.get_or_create(payload.user_id, email=payload.email)
        if payload.display_name and not user.display_name:
            user.display_name = payload.display_name
            await self.db.flush()

        # SCD2 write path: assign_role opens/closes rows so the membership
        # history is preserved. Casbin grouping is synced to the new role
        # immediately (set_role drops prior roles + adds the new one).
        existing = await self.memberships.current_role(payload.user_id, tenant_id)
        membership = await self.memberships.assign_role(
            payload.user_id, tenant_id, payload.role
        )
        if existing is None:
            await permission_service.add_role_for_user_in_domain(
                payload.user_id, payload.role, tenant_id
            )
        else:
            await permission_service.set_role_for_user_in_domain(
                payload.user_id, payload.role, tenant_id
            )
        await self.db.commit()
        await self.db.refresh(membership, attribute_names=["user"])
        return self._to_read(membership)

    async def update_role(
        self,
        actor_id: str,
        tenant_id: str,
        target_user_id: str,
        payload: MemberUpdate,
        platform_role: str | None = None,
    ) -> MemberRead:
        await permission_service.require(
            actor_id, tenant_id, self.OBJECT, "update", platform_role=platform_role
        )

        membership = await self.memberships.current_role(target_user_id, tenant_id)
        if membership is None:
            raise ValueError(f"user {target_user_id} is not a member of this tenant")

        # SCD2 write: assign_role closes the current row and opens a new one with
        # the new role; casbin grouping is resynced so the change takes effect at
        # once (no re-login needed).
        membership = await self.memberships.assign_role(
            target_user_id, tenant_id, payload.role
        )
        await permission_service.set_role_for_user_in_domain(
            target_user_id, payload.role, tenant_id
        )
        await self.db.commit()
        await self.db.refresh(membership, attribute_names=["user"])
        return self._to_read(membership)

    async def remove(
        self,
        actor_id: str,
        tenant_id: str,
        target_user_id: str,
        platform_role: str | None = None,
    ) -> None:
        await permission_service.require(
            actor_id, tenant_id, self.OBJECT, "delete", platform_role=platform_role
        )

        if actor_id == target_user_id:
            raise ValueError("cannot remove yourself")

        membership = await self.memberships.current_role(target_user_id, tenant_id)
        if membership is None:
            raise ValueError(f"user {target_user_id} is not a member of this tenant")

        # SCD2 write: close the active row (history preserved, no physical
        # delete) and strip the casbin grouping so access stops immediately.
        await self.memberships.remove_member(target_user_id, tenant_id)
        await permission_service.remove_user_from_tenant(target_user_id, tenant_id)
        await self.db.commit()
