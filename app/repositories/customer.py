"""Repositories for Customer + CustomerProfile.

``Customer`` is a platform-level global identity (no ``tenant_id``), so
``CustomerRepository`` extends ``BaseRepository`` directly and filters
``is_deleted=False`` manually (like ``GroupRepository``).

``CustomerProfile`` carries ``tenant_id`` (store-scoped), so
``CustomerProfileRepository`` extends ``TenantScopedRepository`` for the store
view. The super_admin cross-store aggregation uses a separate unscoped query
(JOIN Customer) that ignores ``tenant_id``.
"""

from sqlalchemy import select
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
