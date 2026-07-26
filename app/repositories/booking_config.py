"""Booking-config repository.

Extends ``BaseRepository`` directly (NOT ``TenantScopedRepository``): a row's
``tenant_id`` is *nullable* (NULL = platform-wide default), so the
``get_for_tenant`` filter would wrongly exclude platform rows. Scope selection
(platform vs tenant) is done explicitly by the dedicated query methods below.
Mirrors :class:`LlmConfigRepository` / :class:`ModelPricingRepository`.

Multi-tenant isolation note (plan §4.2): the tenant-scoped GET/PUT endpoints
pass ``tenant_id`` from the resolved caller (never the URL/body for store
roles — the API layer enforces that), so this repo is never asked for "another
tenant's" row by a store principal. A platform writer (super_admin) explicitly
reads/writes any tenant's override; that is the intended cross-tenant path.
"""

from sqlalchemy import select

from app.models.booking_config import BookingConfig
from app.repositories.base import BaseRepository


class BookingConfigRepository(BaseRepository[BookingConfig]):
    model = BookingConfig

    async def get_platform(self) -> BookingConfig | None:
        """The platform-wide config row (tenant_id IS NULL)."""
        stmt = select(BookingConfig).where(BookingConfig.tenant_id.is_(None))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_tenant(self, tenant_id: str) -> BookingConfig | None:
        """The tenant-level override row, if any (NULL tenant_id excluded)."""
        stmt = select(BookingConfig).where(BookingConfig.tenant_id == tenant_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
