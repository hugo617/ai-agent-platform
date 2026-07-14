"""Tenant branding config endpoints — read / write the caller's white-label config.

Both endpoints are scoped to the caller's own tenant (resolved from the token via
``get_current_user``), so cross-tenant edits are impossible by construction — the
service only ever receives ``user.tenant_id``.

  - GET  /tenant-config — the caller's branding config (None if unset; the
    frontend falls back to platform defaults). Open to ANY authenticated user of
    the tenant: branding (theme color / logo / display name) applies globally to
    everyone, so a plain member must be able to read it.
  - PUT  /tenant-config — upsert the caller's branding config. Requires
    ``settings:update`` (seeded for owner/admin; super_admin short-circuits via
    ``permission_service.check``).

The login page is unauthenticated, and the platform has no tenant-slug system to
look a tenant up by, so the login page renders the platform default brand and
the tenant brand is applied once the user is authenticated (MVP approach noted in
the plan).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.core.database import get_db
from app.schemas.tenant_config import TenantConfigRead, TenantConfigUpdate
from app.services.tenant_config_service import tenant_config_service

router = APIRouter(prefix="/tenant-config", tags=["settings"])


@router.get(
    "",
    response_model=TenantConfigRead | None,
)
async def get_tenant_config(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TenantConfigRead | None:
    """The caller's tenant branding config. None if no row exists yet.

    Readable by any authenticated member of the tenant (branding applies to
    everyone), not gated on ``settings:read``.
    """
    return await tenant_config_service.get_for_tenant(db, user.tenant_id)


@router.put(
    "",
    response_model=TenantConfigRead,
    dependencies=[Depends(require_permission("settings", "update"))],
)
async def update_tenant_config(
    payload: TenantConfigUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TenantConfigRead:
    """Create or update the caller's tenant branding config (upsert)."""
    return await tenant_config_service.upsert(db, user.tenant_id, payload)
