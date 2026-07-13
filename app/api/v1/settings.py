"""LLM settings endpoints — manage platform-wide and tenant-level provider config.

Two scopes, deliberately separate:

  - **platform** (``/settings/llm/platform``): the fallback config shared by
    every tenant. Only platform super admins may read/write it — no
    tenant-scoped permission grants this, on purpose.
  - **tenant** (``/settings/llm/tenant``): an optional override for the
    caller's own tenant. Requires ``settings:read`` (GET) or ``settings:update``
    (PUT), seeded for owner/admin; super admins also pass via the short-circuit
    in ``permission_service.check``.

A read endpoint for the effective model list (``/settings/models``) is open to
any authenticated user — it backs the agent-creation dropdown and leaks no
secrets (just model names).

Permission granularity: the tenant endpoints use ``settings:read`` (GET) and
``settings:update`` (PUT) — the coarse ``settings:manage`` was split in the
permission-unified-model task so a role can be granted read-only settings.

API keys are *never* returned in plaintext: GET responses carry a masked hint
(``sk-***wxyz``), and PUT accepts an empty/null key to mean "keep the stored
key".
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, require_permission, require_super_admin
from app.core.database import get_db
from app.schemas.llm_config import LlmConfigRead, LlmConfigUpdate
from app.services.llm_config_service import llm_config_service

router = APIRouter(prefix="/settings", tags=["settings"])


# ----- platform-wide config (super admin only) -----


@router.get(
    "/llm/platform",
    response_model=LlmConfigRead | None,
    dependencies=[Depends(require_super_admin())],
)
async def get_platform_llm_config(
    db: AsyncSession = Depends(get_db),
) -> LlmConfigRead | None:
    """The platform-wide LLM config (masked key). None if unset."""
    return await llm_config_service.get_platform(db)


@router.put(
    "/llm/platform",
    response_model=LlmConfigRead,
    dependencies=[Depends(require_super_admin())],
)
async def update_platform_llm_config(
    payload: LlmConfigUpdate,
    db: AsyncSession = Depends(get_db),
) -> LlmConfigRead:
    """Create or update the platform-wide LLM config."""
    return await llm_config_service.upsert_platform(db, payload)


# ----- tenant-level config (owner/admin; super admin short-circuits) -----


@router.get(
    "/llm/tenant",
    response_model=LlmConfigRead | None,
    dependencies=[Depends(require_permission("settings", "read"))],
)
async def get_tenant_llm_config(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LlmConfigRead | None:
    """The caller's tenant-level LLM config (masked key). None if unset."""
    return await llm_config_service.get_tenant(db, user.tenant_id)


@router.put(
    "/llm/tenant",
    response_model=LlmConfigRead,
    dependencies=[Depends(require_permission("settings", "update"))],
)
async def update_tenant_llm_config(
    payload: LlmConfigUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LlmConfigRead:
    """Create or update the caller's tenant-level LLM config."""
    return await llm_config_service.upsert_tenant(db, user.tenant_id, payload)


# ----- effective model list (any authenticated user) -----


@router.get(
    "/models",
    response_model=list[str],
)
async def list_effective_models(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[str]:
    """The selectable model list resolved for the caller's tenant.

    Drives the agent-creation model dropdown. Returns only model names — no
    keys, URLs, or any secret material.
    """
    return await llm_config_service.list_models(db, user.tenant_id)
