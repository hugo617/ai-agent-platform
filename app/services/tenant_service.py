"""Tenant service — create tenants, bootstrap their owners, and (super_admin)
platform-level list / detail / update."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.group import Group
from app.models.tenant import Tenant
from app.repositories.group import GroupRepository, GroupTenantRepository
from app.repositories.tenant import TenantRepository, UserRepository, UserTenantRepository
from app.schemas.tenant import TenantCreate, TenantRead, TenantUpdate
from app.services.errors import NotFoundError
from app.services.permission_service import permission_service


def _to_read(tenant: Tenant, member_count: int = 0) -> TenantRead:
    """Build a TenantRead from a Tenant, injecting the runtime member_count."""
    data = {c.name: getattr(tenant, c.name) for c in tenant.__table__.columns}
    data["member_count"] = member_count
    return TenantRead.model_validate(data)


class TenantService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.tenants = TenantRepository(db)
        self.users = UserRepository(db)
        self.memberships = UserTenantRepository(db)

    async def create_tenant(
        self,
        owner_user_id: str,
        payload: TenantCreate,
        owner_email: str | None = None,
        *,
        created_by: str | None = None,
    ) -> TenantRead:
        """Create a tenant, link the owner, and seed default casbin policies.

        ``created_by`` records the platform user who created this tenant
        (the super_admin's id under the tightened POST policy). The bootstrap /
        dev-seed path may leave it as None.

        Step 7 (knowledge-tiered slice 02): every tenant is born as its own
        one-member Group — a single store IS a chain of one (D8+D10+E2). The
        Group's ``headquarters_tenant_id`` points back at the new tenant so its
        owner/admin derive the ``group_admin`` identity for knowledge. Runs in
        the SAME transaction as steps 1-6, so a failure here rolls the whole
        tenant back (no orphan tenant without a group, AC8).
        """
        # 1. Ensure the user row exists
        await self.users.get_or_create(owner_user_id, email=owner_email)

        # 2. Create the tenant
        tenant = Tenant(name=payload.name, created_by=created_by)
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

        # 6. Initialize a zero-balance token wallet (same transaction). The
        #    chat endpoint's balance gate treats a missing wallet as "no
        #    balance", so every tenant must have one from birth for chats to
        #    work at all. Recharging credits this wallet later.
        from app.services.billing_service import BillingService

        await BillingService(self.db).create_wallet_for_tenant(tenant.id)

        # 7. Auto-group: single store = its own chain. Always create a Group
        #    (name mirrors the tenant, headquarters points at the tenant) and
        #    attach the tenant to it, in this same transaction. Knowledge-tiered
        #    D8 (one-tenant-one-group) + D10 (Group has HQ pointer) + E2
        #    (auto-group at create). Chain stores join an existing group via
        #    ``group_service.attach_tenant`` instead, so this step only fires
        #    for the born-as-its-own-chain case. If anything here raises, the
        #    whole create_tenant rolls back (AC8) — no half-created tenant.
        group = Group(name=tenant.name, headquarters_tenant_id=tenant.id)
        await GroupRepository(self.db).add(group)
        await GroupTenantRepository(self.db).attach(group.id, tenant.id)

        await self.db.commit()
        return _to_read(tenant, member_count=1)

    async def list_user_tenants(self, user_id: str) -> list[TenantRead]:
        memberships = await self.memberships.list_for_user(user_id)
        tenants: list[TenantRead] = []
        for m in memberships:
            t = await self.tenants.get_by_id(m.tenant_id)
            if t is not None:
                tenants.append(_to_read(t))
        return tenants

    # ----------------------------------------------- platform-level (super_admin)

    async def list_all(self) -> list[TenantRead]:
        """All tenants with member_count (platform-level, super_admin only).

        The route layer enforces ``require_super_admin()``; the service itself
        does not re-check the role.
        """
        rows = await self.tenants.list_all_with_member_count()
        return [_to_read(t, c) for t, c in rows]

    async def get_detail(self, tenant_id: str) -> TenantRead:
        """Single tenant with member_count; raises NotFoundError if absent."""
        row = await self.tenants.get_detail_with_member_count(tenant_id)
        if row is None:
            raise NotFoundError(f"tenant {tenant_id} not found")
        tenant, count = row
        return _to_read(tenant, count)

    async def update(self, tenant_id: str, payload: TenantUpdate) -> TenantRead:
        """Partially update a tenant (super_admin only).

        Only the fields the caller actually provides are touched; the rest are
        left unchanged. Returns the updated read view with a fresh member_count.
        """
        row = await self.tenants.get_detail_with_member_count(tenant_id)
        if row is None:
            raise NotFoundError(f"tenant {tenant_id} not found")
        tenant, _ = row
        changes = payload.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(tenant, field, value)
        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(tenant)
        # Recompute member_count after the update (count is unaffected by name
        # / status / description edits, but re-querying keeps the contract honest).
        detail = await self.tenants.get_detail_with_member_count(tenant_id)
        count = detail[1] if detail is not None else 0
        return _to_read(tenant, count)
