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

The same two-scope pattern backs the **embedding** config
(``/settings/embedding/{platform,tenant}``) used by the RAG pipeline (priority
57). It is a separate table from the LLM config because the embeddings endpoint
differs from the chat LLM (DeepSeek does NOT expose embeddings), so they need
independent api_key / base_url.

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
from app.schemas.embedding_config import EmbeddingConfigRead, EmbeddingConfigUpdate
from app.schemas.llm_config import LlmConfigRead, LlmConfigUpdate
from app.services.embedding_config_service import embedding_config_service
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


# ===========================================================================
# Embedding config (RAG pipeline, priority 57).
# Separate table from the LLM config above because the embeddings endpoint
# differs from the chat LLM (DeepSeek does NOT expose embeddings). Same two-
# scope pattern: platform (super admin) + tenant (owner/admin), tenant >
# platform > env fallback. See EmbeddingConfigService.get_effective.
# ===========================================================================


# ----- platform-wide embedding config (super admin only) -----


@router.get(
    "/embedding/platform",
    response_model=EmbeddingConfigRead | None,
    dependencies=[Depends(require_super_admin())],
)
async def get_platform_embedding_config(
    db: AsyncSession = Depends(get_db),
) -> EmbeddingConfigRead | None:
    """The platform-wide embedding config (masked key). None if unset."""
    return await embedding_config_service.get_platform(db)


@router.put(
    "/embedding/platform",
    response_model=EmbeddingConfigRead,
    dependencies=[Depends(require_super_admin())],
)
async def update_platform_embedding_config(
    payload: EmbeddingConfigUpdate,
    db: AsyncSession = Depends(get_db),
) -> EmbeddingConfigRead:
    """Create or update the platform-wide embedding config."""
    return await embedding_config_service.upsert_platform(db, payload)


# ----- tenant-level embedding config (owner/admin; super admin short-circuits) -----


@router.get(
    "/embedding/tenant",
    response_model=EmbeddingConfigRead | None,
    dependencies=[Depends(require_permission("settings", "read"))],
)
async def get_tenant_embedding_config(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmbeddingConfigRead | None:
    """The caller's tenant-level embedding config (masked key). None if unset."""
    return await embedding_config_service.get_tenant(db, user.tenant_id)


@router.put(
    "/embedding/tenant",
    response_model=EmbeddingConfigRead,
    dependencies=[Depends(require_permission("settings", "update"))],
)
async def update_tenant_embedding_config(
    payload: EmbeddingConfigUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmbeddingConfigRead:
    """Create or update the caller's tenant-level embedding config."""
    return await embedding_config_service.upsert_tenant(db, user.tenant_id, payload)
