"""Customer service — global identity + per-tenant profile management.

Permission model has two access patterns:

- **Store view** (tenant-scoped): store users (owner/admin/member) operate on
  their own tenant's profiles via ``require_permission('customers', act)``.
  super_admin also goes through these endpoints but sees all stores (the
  repository's ``list_all`` ignores ``tenant_id``).
- **HQ view** (platform-level): super_admin reads the cross-store aggregation
  via ``require_super_admin()`` — a single Customer with every store's profile.

Core create logic: "create-or-reuse identity, then attach a profile".
- ``get_by_identity(payload.identity_key)`` → exists? reuse Customer, build
  Profile(this tenant); not exists? build Customer + Profile together.
- Duplicate check: if this store already has a live profile for that customer,
  raise BizError(400) — one profile per store.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer, CustomerProfile
from app.repositories.customer import (
    CustomerProfileRepository,
    CustomerRepository,
    batch_tenant_info,
)
from app.schemas.customer import (
    CustomerBrief,
    CustomerProfileBrief,
    CustomerProfileCreate,
    CustomerProfileRead,
    CustomerProfileUpdate,
    CustomerRead,
    CustomerStatistics,
)
from app.schemas.group import TenantBrief
from app.services.data_scope import DataScopeService
from app.services.errors import BizError, NotFoundError
from app.services.permission_service import is_cross_tenant_viewer, permission_service


class CustomerService:
    OBJECT = "customers"

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.customers = CustomerRepository(db)
        self.profiles = CustomerProfileRepository(db)

    # ------------------------------------------------------------- helpers

    async def _customer_brief(self, customer: Customer) -> CustomerBrief:
        return CustomerBrief(
            id=customer.id,
            identity_key=customer.identity_key,
            name=customer.name,
            gender=customer.gender,
            birthday=customer.birthday,
            avatar=customer.avatar,
        )

    async def _profile_briefs(
        self, profiles: list[CustomerProfile]
    ) -> list[CustomerProfileBrief]:
        """Expand a list of profiles into briefs with tenant names batched."""
        tenant_ids = list({p.tenant_id for p in profiles})
        names = await batch_tenant_info(self.db, tenant_ids)
        return [
            CustomerProfileBrief(
                id=p.id,
                tenant=TenantBrief(id=p.tenant_id, name=names.get(p.tenant_id)),
                remark=p.remark,
                tags=p.tags or {},
                status=p.status,
                last_visit_at=p.last_visit_at,
            )
            for p in profiles
        ]

    async def _to_profile_read(
        self, profile: CustomerProfile, customer: Customer
    ) -> CustomerProfileRead:
        data = {c.name: getattr(profile, c.name) for c in profile.__table__.columns}
        data["customer"] = await self._customer_brief(customer)
        return CustomerProfileRead.model_validate(data)

    async def _to_customer_read(
        self, customer: Customer, profiles: list[CustomerProfile]
    ) -> CustomerRead:
        briefs = await self._profile_briefs(profiles)
        data = {c.name: getattr(customer, c.name) for c in customer.__table__.columns}
        data["profiles"] = briefs
        data["profile_count"] = len(briefs)
        return CustomerRead.model_validate(data)

    async def _get_live_customer(self, customer_id: str) -> Customer:
        customer = await self.customers.get(customer_id)
        if customer is None:
            raise NotFoundError(f"客户不存在: {customer_id}")
        return customer

    async def _get_live_profile(
        self, tenant_id: str, profile_id: str
    ) -> CustomerProfile:
        profile = await self.profiles.get_for_tenant(profile_id, tenant_id)
        if profile is None:
            raise NotFoundError(f"客户档案不存在: {profile_id}")
        return profile

    # ------------------------------------------------------- store-scoped read

    async def list_profiles(
        self,
        actor_id: str,
        tenant_id: str,
        platform_role: str | None = None,
    ) -> list[CustomerProfileRead]:
        """Store view filtered by the caller's row-level data scope.

        Platform viewers (super_admin / hq_staff) resolve to ``all`` (every
        store); tenant roles resolve to tenant/group/self per their role's
        ``data_scope`` (权限重构系列 3/4). Permission check still runs for
        non-platform users (``customers:read``).
        """
        is_cross_tenant = is_cross_tenant_viewer(platform_role)
        if not is_cross_tenant:
            await permission_service.require(
                actor_id,
                tenant_id,
                self.OBJECT,
                "read",
                platform_role=platform_role,
            )
        resolved = await DataScopeService(self.db).resolve(
            actor_id, tenant_id, platform_role
        )
        profiles = await self.profiles.list_for_scope(
            scope=resolved.scope,
            tenant_id=tenant_id,
            group_tenant_ids=resolved.tenant_ids or None,
            owner_user_id=resolved.owner_user_id,
        )
        # Batch-load customers to avoid N+1.
        customer_ids = list({p.customer_id for p in profiles})
        customers_map: dict[str, Customer] = {}
        for cid in customer_ids:
            c = await self.customers.get(cid)
            if c is not None:
                customers_map[cid] = c
        result = []
        for p in profiles:
            c = customers_map.get(p.customer_id)
            if c is None:
                # Orphaned profile (customer soft-deleted); skip.
                continue
            result.append(await self._to_profile_read(p, c))
        return result

    async def statistics(
        self,
        actor_id: str,
        tenant_id: str,
        platform_role: str | None = None,
    ) -> CustomerStatistics:
        """Customer counts for the dashboard card.

        Store scope = live profiles in this store (total / active / last_7d_new);
        super_admin scope = live identities across stores (total / with-active-
        profile / last_7d_new). Mirrors the dual read pattern of ``list_profiles``.
        """
        is_cross_tenant = is_cross_tenant_viewer(platform_role)
        if not is_cross_tenant:
            await permission_service.require(
                actor_id,
                tenant_id,
                self.OBJECT,
                "read",
                platform_role=platform_role,
            )
        since_7d = datetime.now(UTC) - timedelta(days=7)
        if is_cross_tenant:
            data = await self.customers.statistics_all_global(since_7d=since_7d)
        else:
            data = await self.profiles.statistics_for_tenant(tenant_id, since_7d=since_7d)
        return CustomerStatistics(**data)

    # ------------------------------------------------------- store-scoped write

    async def create_profile(
        self,
        actor_id: str,
        tenant_id: str,
        payload: CustomerProfileCreate,
        platform_role: str | None = None,
    ) -> CustomerProfileRead:
        await permission_service.require(
            actor_id,
            tenant_id,
            self.OBJECT,
            "create",
            platform_role=platform_role,
        )
        # Create-or-reuse the global identity.
        customer = await self.customers.get_by_identity(payload.identity_key)
        if customer is None:
            customer = Customer(
                identity_key=payload.identity_key,
                name=payload.name,
                gender=payload.gender,
                birthday=payload.birthday,
            )
            await self.customers.add(customer)
        else:
            # Keep global identity fields in sync with the latest provided
            # values when reusing (MVP: last-write-wins, no conflict detection).
            customer.name = payload.name
            customer.gender = payload.gender
            customer.birthday = payload.birthday

        # Duplicate check: one live profile per (customer, tenant).
        existing = await self.profiles.get_by_customer_tenant(
            customer.id, tenant_id
        )
        if existing is not None:
            raise BizError("该客户在本门店已有档案")

        profile = CustomerProfile(
            customer_id=customer.id,
            tenant_id=tenant_id,
            remark=payload.remark,
            tags=payload.tags,
            status=payload.status,
            created_by=actor_id,
        )
        await self.profiles.add(profile)
        await self.db.commit()
        # Re-fetch so server defaults (created_at/updated_at) are loaded.
        fresh_p = await self.profiles.get_for_tenant(profile.id, tenant_id)
        assert fresh_p is not None  # just created
        fresh_c = await self._get_live_customer(customer.id)
        return await self._to_profile_read(fresh_p, fresh_c)

    async def update_profile(
        self,
        actor_id: str,
        tenant_id: str,
        profile_id: str,
        payload: CustomerProfileUpdate,
        platform_role: str | None = None,
    ) -> CustomerProfileRead:
        await permission_service.require(
            actor_id,
            tenant_id,
            self.OBJECT,
            "update",
            platform_role=platform_role,
        )
        profile = await self._get_live_profile(tenant_id, profile_id)
        customer = await self._get_live_customer(profile.customer_id)
        data = payload.model_dump(exclude_unset=True)
        # Sync global-identity fields to the Customer.
        for key in ("name", "gender", "birthday"):
            if key in data:
                setattr(customer, key, data[key])
        # Store-private fields go on the profile.
        for key in ("remark", "tags", "status"):
            if key in data:
                setattr(profile, key, data[key])
        await self.db.flush()
        await self.db.commit()
        # Re-fetch: commit expires ORM objects (MissingGreenlet guard).
        fresh_p = await self.profiles.get_for_tenant(profile_id, tenant_id)
        assert fresh_p is not None
        fresh_c = await self._get_live_customer(customer.id)
        return await self._to_profile_read(fresh_p, fresh_c)

    async def delete_profile(
        self,
        actor_id: str,
        tenant_id: str,
        profile_id: str,
        platform_role: str | None = None,
    ) -> None:
        """Soft-delete this store's profile. The Customer global identity is
        NEVER deleted here — other stores may still reference it."""
        await permission_service.require(
            actor_id,
            tenant_id,
            self.OBJECT,
            "delete",
            platform_role=platform_role,
        )
        profile = await self._get_live_profile(tenant_id, profile_id)
        profile.is_deleted = True
        profile.deleted_at = datetime.now(UTC)
        await self.db.flush()
        await self.db.commit()

    # --------------------------------------------------------- HQ aggregation

    async def list_customers_hq(
        self,
    ) -> list[CustomerRead]:
        """super_admin only: all customers with their cross-store profiles."""
        customers = await self.customers.list_all()
        result = []
        for c in customers:
            profiles = await self.profiles.list_for_customer(c.id)
            result.append(await self._to_customer_read(c, profiles))
        return result

    async def get_customer_aggregate(
        self, customer_id: str
    ) -> CustomerRead:
        """super_admin only: one customer with all store profiles."""
        customer = await self._get_live_customer(customer_id)
        profiles = await self.profiles.list_for_customer(customer.id)
        return await self._to_customer_read(customer, profiles)
