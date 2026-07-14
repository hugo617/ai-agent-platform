"""Repositories for Customer + CustomerProfile.

``Customer`` is a platform-level global identity (no ``tenant_id``), so
``CustomerRepository`` extends ``BaseRepository`` directly and filters
``is_deleted=False`` manually (like ``GroupRepository``).

``CustomerProfile`` carries ``tenant_id`` (store-scoped), so
``CustomerProfileRepository`` extends ``TenantScopedRepository`` for the store
view. The super_admin cross-store aggregation uses a separate unscoped query
(JOIN Customer) that ignores ``tenant_id``.
"""

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.models.customer import Customer, CustomerProfile
from app.models.tenant import Tenant
from app.repositories.base import BaseRepository, TenantScopedRepository


class CustomerRepository(BaseRepository[Customer]):
    """Global-identity CRUD (platform-level, cross-store, soft-deleted)."""

    model = Customer

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def get(self, customer_id: str) -> Customer | None:
        """Fetch a live (non-deleted) customer by id."""
        stmt = select(Customer).where(
            Customer.id == customer_id, Customer.is_deleted.is_(False)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_by_identity(self, identity_key: str) -> Customer | None:
        """Look up a live customer by identity_key (cross-store recognition)."""
        stmt = select(Customer).where(
            Customer.identity_key == identity_key,
            Customer.is_deleted.is_(False),
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list_all(self) -> list[Customer]:
        """All live customers (super_admin view), newest first."""
        stmt = (
            select(Customer)
            .where(Customer.is_deleted.is_(False))
            .order_by(Customer.created_at.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def search(self, *, keyword: str, limit: int = 5) -> list[Customer]:
        """Case-insensitive match on name OR identity_key across all stores.

        Used by the global search endpoint for cross-tenant viewers
        (super_admin / hq_staff): the Customer table is platform-level (no
        ``tenant_id``), so no tenant filter is applied here.
        """
        like = f"%{keyword}%"
        stmt = (
            select(Customer)
            .where(
                Customer.is_deleted.is_(False),
                or_(
                    Customer.name.ilike(like),
                    Customer.identity_key.ilike(like),
                ),
            )
            .order_by(Customer.created_at.desc())
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def statistics_all_global(
        self, *, since_7d: datetime
    ) -> dict[str, int]:
        """Platform-level customer identity stats (super_admin overview).

        Counts live identities (Customer table, cross-store):
        - ``total``         — all-time live identities
        - ``active``        — identities with at least one active profile
        - ``last_7d_new``   — identities created in the last 7 days
        """
        total_stmt = select(func.count()).select_from(Customer).where(
            Customer.is_deleted.is_(False)
        )
        total = int((await self.db.execute(total_stmt)).scalar_one())
        # "Active" customers = those with at least one live active profile.
        active_subq = (
            select(CustomerProfile.customer_id)
            .where(
                CustomerProfile.is_deleted.is_(False),
                CustomerProfile.status == "active",
            )
            .distinct()
            .subquery()
        )
        active_stmt = (
            select(func.count())
            .select_from(Customer)
            .where(
                Customer.is_deleted.is_(False),
                Customer.id.in_(select(active_subq.c.customer_id)),
            )
        )
        active = int((await self.db.execute(active_stmt)).scalar_one())
        new_7d_stmt = (
            select(func.count())
            .select_from(Customer)
            .where(
                Customer.is_deleted.is_(False),
                Customer.created_at >= since_7d,
            )
        )
        new_7d = int((await self.db.execute(new_7d_stmt)).scalar_one())
        return {"total": total, "active": active, "last_7d_new": new_7d}


class CustomerProfileRepository(TenantScopedRepository[CustomerProfile]):
    """Per-store customer profiles, tenant-scoped on reads."""

    model = CustomerProfile

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def get_for_tenant(
        self, obj_id: str, tenant_id: str
    ) -> CustomerProfile | None:
        """A store's live profile by id (enforces tenant_id + is_deleted)."""
        stmt = select(CustomerProfile).where(
            CustomerProfile.id == obj_id,
            CustomerProfile.tenant_id == tenant_id,
            CustomerProfile.is_deleted.is_(False),
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list_for_tenant(self, tenant_id: str) -> list[CustomerProfile]:
        """All live profiles in a store, newest first."""
        stmt = (
            select(CustomerProfile)
            .where(
                CustomerProfile.tenant_id == tenant_id,
                CustomerProfile.is_deleted.is_(False),
            )
            .order_by(CustomerProfile.created_at.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def list_all(self) -> list[CustomerProfile]:
        """All live profiles across stores (super_admin aggregation)."""
        stmt = (
            select(CustomerProfile)
            .where(CustomerProfile.is_deleted.is_(False))
            .order_by(CustomerProfile.created_at.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def search_for_tenant(
        self, *, keyword: str, tenant_id: str, limit: int = 100
    ) -> list[CustomerProfile]:
        """Store-scoped name/identity_key search (joins the global Customer).

        ``name`` and ``identity_key`` live on the platform-level Customer; this
        store's profiles carry only ``remark``/``tags``/``status``. We JOIN to
        Customer so a store user can find a profile by the customer's name or
        identity, while the ``tenant_id`` filter keeps isolation in the
        repository layer (per the multi-tenant rule).
        """
        like = f"%{keyword}%"
        stmt = (
            select(CustomerProfile)
            .join(Customer, Customer.id == CustomerProfile.customer_id)
            .where(
                CustomerProfile.tenant_id == tenant_id,
                CustomerProfile.is_deleted.is_(False),
                Customer.is_deleted.is_(False),
                or_(
                    Customer.name.ilike(like),
                    Customer.identity_key.ilike(like),
                ),
            )
            .order_by(CustomerProfile.created_at.desc())
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def search_for_scope(
        self,
        *,
        keyword: str,
        scope: str,
        tenant_id: str,
        group_tenant_ids: list[str] | None = None,
        owner_user_id: str | None = None,
        limit: int = 100,
    ) -> list[CustomerProfile]:
        """Keyword search that honours the resolved row-level data scope.

        Mirrors ``list_for_scope`` (same scope semantics + is_deleted filter)
        and layers the Customer name/identity_key ILIKE on top, so a search
        returns exactly the same population the user sees without a search —
        no silent narrowing (group) or broadening (self) when a keyword is
        present. Tenant/scope isolation stays in this repository layer.

        - ``all``     → ignore tenant_id (cross-store, platform viewers)
        - ``tenant``  → ``tenant_id == tenant_id``
        - ``group``   → ``tenant_id IN (group_tenant_ids)``
        - ``self``    → ``tenant_id == tenant_id AND created_by == owner_user_id``
        """
        like = f"%{keyword}%"
        if scope == "all":
            tenant_clause = CustomerProfile.is_deleted.is_(False)
        elif scope == "group":
            ids = group_tenant_ids or [tenant_id]
            tenant_clause = CustomerProfile.is_deleted.is_(False) & (
                CustomerProfile.tenant_id.in_(ids)
            )
        elif scope == "self":
            tenant_clause = (
                CustomerProfile.is_deleted.is_(False)
                & (CustomerProfile.tenant_id == tenant_id)
                & (CustomerProfile.created_by == owner_user_id)
            )
        else:  # "tenant" (safe fallback)
            tenant_clause = CustomerProfile.is_deleted.is_(False) & (
                CustomerProfile.tenant_id == tenant_id
            )
        stmt = (
            select(CustomerProfile)
            .join(Customer, Customer.id == CustomerProfile.customer_id)
            .where(
                tenant_clause,
                Customer.is_deleted.is_(False),
                or_(
                    Customer.name.ilike(like),
                    Customer.identity_key.ilike(like),
                ),
            )
            .order_by(CustomerProfile.created_at.desc())
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_by_customer_tenant(
        self, customer_id: str, tenant_id: str
    ) -> CustomerProfile | None:
        """Does this store already have a live profile for this customer?

        Used by create_profile to reject duplicates (one profile per store).
        """
        stmt = select(CustomerProfile).where(
            CustomerProfile.customer_id == customer_id,
            CustomerProfile.tenant_id == tenant_id,
            CustomerProfile.is_deleted.is_(False),
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list_for_customer(self, customer_id: str) -> list[CustomerProfile]:
        """All live profiles for one customer across stores (HQ aggregation)."""
        stmt = (
            select(CustomerProfile)
            .where(
                CustomerProfile.customer_id == customer_id,
                CustomerProfile.is_deleted.is_(False),
            )
            .order_by(CustomerProfile.created_at.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def list_for_scope(
        self,
        *,
        scope: str,
        tenant_id: str,
        group_tenant_ids: list[str] | None = None,
        owner_user_id: str | None = None,
    ) -> list[CustomerProfile]:
        """Live profiles filtered by the caller's resolved row-level data scope.

        Driven by ``DataScopeService.resolve`` (权限重构系列 3/4); this method
        takes the *already-resolved* scope so the Repository stays free of any
        Service/permission dependency (single-direction: Service → Repository).

        - ``all``     → ignore tenant_id (cross-store, for platform viewers)
        - ``tenant``  → ``tenant_id == tenant_id`` (the pre-feature default)
        - ``group``   → ``tenant_id IN (group_tenant_ids)``
        - ``self``    → ``tenant_id == tenant_id AND created_by == owner_user_id``
        """
        base = CustomerProfile.is_deleted.is_(False)
        if scope == "all":
            where = base
        elif scope == "group":
            ids = group_tenant_ids or [tenant_id]
            where = base & CustomerProfile.tenant_id.in_(ids)
        elif scope == "self":
            where = (
                base
                & (CustomerProfile.tenant_id == tenant_id)
                & (CustomerProfile.created_by == owner_user_id)
            )
        else:  # "tenant" (also the safe fallback)
            where = base & (CustomerProfile.tenant_id == tenant_id)
        stmt = (
            select(CustomerProfile)
            .where(where)
            .order_by(CustomerProfile.created_at.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def statistics_for_tenant(
        self, tenant_id: str, *, since_7d: datetime
    ) -> dict[str, int]:
        """Store-level customer profile stats (dashboard card).

        Counts live profiles in this store:
        - ``total``         — all-time live profiles
        - ``active``        — profiles with ``status='active'``
        - ``last_7d_new``   — profiles created in the last 7 days
        """
        base = CustomerProfile.is_deleted.is_(False)

        def _count(extra):
            # Build a COUNT(*) already — return it directly (do NOT wrap in
            # another count(): that would count the single result row = 1).
            stmt = (
                select(func.count())
                .select_from(CustomerProfile)
                .where(base, CustomerProfile.tenant_id == tenant_id)
            )
            if extra is not None:
                stmt = stmt.where(extra)
            return stmt

        total = int((await self.db.execute(_count(None))).scalar_one())
        active = int(
            (await self.db.execute(_count(CustomerProfile.status == "active"))).scalar_one()
        )
        new_7d = int(
            (await self.db.execute(_count(CustomerProfile.created_at >= since_7d))).scalar_one()
        )
        return {"total": total, "active": active, "last_7d_new": new_7d}


async def batch_tenant_info(
    db: AsyncSession, tenant_ids: list[str]
) -> dict[str, str | None]:
    """Return ``{tenant_id: tenant_name}`` for the given tenants.

    Used when building the cross-store CustomerRead to expand each profile's
    tenant name without N+1 queries.
    """
    if not tenant_ids:
        return {}
    stmt = select(Tenant.id, Tenant.name).where(Tenant.id.in_(tenant_ids))
    rows = await db.execute(stmt)
    return {tid: name for tid, name in rows.all()}


# Re-export Base for type hints in callers that need it.
__all__ = [
    "Base",
    "CustomerRepository",
    "CustomerProfileRepository",
    "batch_tenant_info",
]
