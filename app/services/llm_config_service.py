"""LLM config service — resolve, read (masked), and write the provider config.

The central method is :meth:`get_effective`, which walks the three-level
fallback chain (tenant > platform > env) and returns the *decrypted* config
ready to hand to ``stream_agent``. The read endpoints (:meth:`get_platform`,
:meth:`get_tenant`) only ever return masked keys.

Writes go through upserts that enforce "one active row per scope" — there is
no DB unique constraint, so this service is the sole place that guarantee is
made (see the model docstring for why).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.core.config import settings
from app.models.llm_config import LlmConfig
from app.repositories.llm_config import LlmConfigRepository
from app.schemas.llm_config import (
    EffectiveLlmConfig,
    LlmConfigRead,
    LlmConfigUpdate,
)


def _to_read(row: LlmConfig) -> LlmConfigRead:
    return LlmConfigRead(
        id=row.id,
        tenant_id=row.tenant_id,
        api_key_hint=row.api_key_hint,
        base_url=row.base_url,
        default_model=row.default_model,
        available_models=list(row.available_models),
        is_active=row.is_active,
        updated_at=row.updated_at,
    )


class LlmConfigService:
    async def get_effective(self, db: AsyncSession, tenant_id: str) -> EffectiveLlmConfig:
        """Resolve the active config via tenant > platform > env fallback.

        Returns a config with a *decrypted* API key — for internal use only,
        never serialize it to an API response.
        """
        repo = LlmConfigRepository(db)
        row = await repo.get_for_tenant(tenant_id)
        if row is None:
            row = await repo.get_platform()
        if row is not None:
            return EffectiveLlmConfig.from_resolved(
                api_key=crypto.decrypt(row.api_key_encrypted),
                base_url=row.base_url,
                default_model=row.default_model,
                available_models=list(row.available_models),
            )
        # No DB config at all — fall back to environment defaults.
        return EffectiveLlmConfig.from_resolved(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            default_model=settings.openai_model,
            # The env path exposes a single model; the UI lists it.
            available_models=[settings.openai_model],
        )

    async def get_platform(self, db: AsyncSession) -> LlmConfigRead | None:
        row = await LlmConfigRepository(db).get_platform()
        return _to_read(row) if row else None

    async def get_tenant(self, db: AsyncSession, tenant_id: str) -> LlmConfigRead | None:
        row = await LlmConfigRepository(db).get_for_tenant(tenant_id)
        return _to_read(row) if row else None

    async def _upsert(
        self,
        db: AsyncSession,
        payload: LlmConfigUpdate,
        existing: LlmConfig | None,
        *,
        tenant_id: str | None,
    ) -> LlmConfigRead:
        base_url = payload.base_url if payload.base_url is not None else (
            existing.base_url if existing else settings.openai_base_url
        )
        default_model = payload.default_model if payload.default_model is not None else (
            existing.default_model if existing else settings.openai_model
        )
        available_models = (
            payload.available_models
            if payload.available_models is not None
            else (list(existing.available_models) if existing else [default_model])
        )

        if existing is not None:
            # Rotate the key only when a new plaintext is supplied; an empty
            # api_key means "keep the stored key".
            if payload.api_key:
                existing.api_key_encrypted = crypto.encrypt(payload.api_key)
                existing.api_key_hint = crypto.mask_api_key(payload.api_key)
            existing.base_url = base_url
            existing.default_model = default_model
            existing.available_models = available_models
            row = existing
        else:
            plaintext = payload.api_key or settings.openai_api_key
            row = LlmConfig(
                tenant_id=tenant_id,
                api_key_encrypted=crypto.encrypt(plaintext),
                api_key_hint=crypto.mask_api_key(plaintext),
                base_url=base_url,
                default_model=default_model,
                available_models=available_models,
            )
            db.add(row)
        await db.flush()
        await db.commit()
        await db.refresh(row)
        return _to_read(row)

    async def upsert_platform(self, db: AsyncSession, payload: LlmConfigUpdate) -> LlmConfigRead:
        existing = await LlmConfigRepository(db).get_platform()
        return await self._upsert(db, payload, existing, tenant_id=None)

    async def upsert_tenant(
        self, db: AsyncSession, tenant_id: str, payload: LlmConfigUpdate
    ) -> LlmConfigRead:
        existing = await LlmConfigRepository(db).get_for_tenant(tenant_id)
        return await self._upsert(db, payload, existing, tenant_id=tenant_id)

    async def list_models(self, db: AsyncSession, tenant_id: str) -> list[str]:
        """The selectable model list for the effective config (agents dropdown)."""
        effective = await self.get_effective(db, tenant_id)
        return effective.available_models


llm_config_service = LlmConfigService()
