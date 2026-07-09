"""Tenant service — create tenants and bootstrap their owners."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.repositories.tenant import TenantRepository, UserRepository, UserTenantRepository
from app.schemas.tenant import TenantCreate, TenantRead
from app.services.permission_service import permission_service


class TenantService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.tenants = TenantRepository(db)
        self.users = UserRepository(db)
        self.memberships = UserTenantRepository(db)

    async def create_tenant(
        self, owner_user_id: str, payload: TenantCreate, owner_email: str | None = None
    ) -> TenantRead:
        """Create a tenant, link the owner, and seed default casbin policies."""
        # 1. Ensure the user row exists
        await self.users.get_or_create(owner_user_id, email=owner_email)

        # 2. Create the tenant
        tenant = Tenant(name=payload.name)
        await self.tenants.add(tenant)

        # 3. Seed the owner/admin/member display roles FIRST (idempotent) so the
        #    role dropdown is populated and seed_tenant_defaults can resolve the
        #    role ids when writing role_permissions SCD2 rows.
        from app.services.rbac_service import RbacService

        await RbacService(self.db).seed_defaults(tenant.id)

        # 4. Link owner with the "owner" role (SCD2 write path: assign_role opens
        #    a current-state user_tenants row that mirrors the casbin grouping).
        await self.memberships.assign_role(owner_user_id, tenant.id, "owner")

        # 5. Seed default permission policies: casbin policies + permissions +
        #    role_permissions SCD2 current rows, all from the single source of
        #    truth (permission_service.DEFAULT_*_PERMS). Pass ``db`` so the SCD2
        #    tables are seeded in lockstep with casbin.
        await permission_service.seed_tenant_defaults(
            tenant.id, owner_user_id, db=self.db
        )

        await self.db.commit()
        return TenantRead.model_validate(tenant)

    async def list_user_tenants(self, user_id: str) -> list[TenantRead]:
        memberships = await self.memberships.list_for_user(user_id)
        tenants: list[TenantRead] = []
        for m in memberships:
            t = await self.tenants.get_by_id(m.tenant_id)
            if t is not None:
                tenants.append(TenantRead.model_validate(t))
        return tenants
