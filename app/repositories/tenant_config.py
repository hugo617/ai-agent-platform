"""Tenant branding config repository.

Extends ``BaseRepository`` directly (like ``LlmConfigRepository``): the row's
``tenant_id`` is the natural key (one row per tenant), and every method is
explicitly scoped by ``tenant_id`` so cross-tenant access is impossible at the
data-access layer.
"""

from sqlalchemy import select

from app.models.tenant_config import TenantConfig
from app.repositories.base import BaseRepository


class TenantConfigRepository(BaseRepository[TenantConfig]):
    model = TenantConfig

    async def get_for_tenant(self, tenant_id: str) -> TenantConfig | None:
        """The single branding row for this tenant, if any."""
        stmt = select(TenantConfig).where(TenantConfig.tenant_id == tenant_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
