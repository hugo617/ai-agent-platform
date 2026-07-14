"""Tenant branding config service — read and upsert one tenant's white-label config.

A thin orchestration layer over ``TenantConfigRepository``. The single ``upsert``
is the sole write path: it creates the row if absent, otherwise patches the
existing row. Multi-tenant isolation comes from the repository (every query is
scoped by ``tenant_id``); the service only ever passes the caller's tenant.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant_config import TenantConfig
from app.repositories.tenant_config import TenantConfigRepository
from app.schemas.tenant_config import TenantConfigRead, TenantConfigUpdate


def _to_read(row: TenantConfig) -> TenantConfigRead:
    return TenantConfigRead(
        id=row.id,
        tenant_id=row.tenant_id,
        display_name=row.display_name,
        logo_url=row.logo_url,
        theme_color=row.theme_color,
        login_text=row.login_text,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class TenantConfigService:
    async def get_for_tenant(
        self, db: AsyncSession, tenant_id: str
    ) -> TenantConfigRead | None:
        row = await TenantConfigRepository(db).get_for_tenant(tenant_id)
        return _to_read(row) if row else None

    async def upsert(
        self, db: AsyncSession, tenant_id: str, payload: TenantConfigUpdate
    ) -> TenantConfigRead:
        """Create or update the branding row for this tenant.

        Every field on the payload is authoritative: the frontend sends all
        four on save, so a None value means "clear this field".
        """
        repo = TenantConfigRepository(db)
        existing = await repo.get_for_tenant(tenant_id)
        if existing is not None:
            existing.display_name = payload.display_name
            existing.logo_url = payload.logo_url
            existing.theme_color = payload.theme_color
            existing.login_text = payload.login_text
            row = existing
        else:
            row = TenantConfig(
                tenant_id=tenant_id,
                display_name=payload.display_name,
                logo_url=payload.logo_url,
                theme_color=payload.theme_color,
                login_text=payload.login_text,
            )
            db.add(row)
        await db.flush()
        await db.commit()
        await db.refresh(row)
        return _to_read(row)


tenant_config_service = TenantConfigService()
