"""Embedding config service — resolve, read (masked), and write the config.

The central method is :meth:`get_effective`, which walks the three-level
fallback chain (tenant > platform > env) and returns the *decrypted* config
ready to hand to ``EmbeddingService``. The read endpoints (:meth:`get_platform`,
:meth:`get_tenant`) only ever return masked keys.

Writes go through upserts that enforce "one active row per scope" — there is
no DB unique constraint, so this service is the sole place that guarantee is
made (see the model docstring for why). Mirrors ``LlmConfigService`` but drops
the available_models handling.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.core.config import settings
from app.models.embedding_config import EmbeddingConfig
from app.repositories.embedding_config import EmbeddingConfigRepository
from app.schemas.embedding_config import (
    EffectiveEmbeddingConfig,
    EmbeddingConfigRead,
    EmbeddingConfigUpdate,
)


def _to_read(row: EmbeddingConfig) -> EmbeddingConfigRead:
    return EmbeddingConfigRead(
        id=row.id,
        tenant_id=row.tenant_id,
        api_key_hint=row.api_key_hint,
        base_url=row.base_url,
        model=row.model,
        is_active=row.is_active,
        updated_at=row.updated_at,
    )


class EmbeddingConfigService:
    async def get_effective(
        self, db: AsyncSession, tenant_id: str
    ) -> EffectiveEmbeddingConfig:
        """Resolve the active config via tenant > platform > env fallback.

        Returns a config with a *decrypted* API key — for internal use only,
        never serialize it to an API response.
        """
        repo = EmbeddingConfigRepository(db)
        row = await repo.get_for_tenant(tenant_id)
        if row is None:
            row = await repo.get_platform()
        if row is not None:
            return EffectiveEmbeddingConfig.from_resolved(
                api_key=crypto.decrypt(row.api_key_encrypted),
                base_url=row.base_url,
                model=row.model,
            )
        # No DB config at all — fall back to environment defaults.
        return EffectiveEmbeddingConfig.from_resolved(
            api_key=settings.embedding_api_key,
            base_url=settings.embedding_base_url,
            model=settings.embedding_model,
        )

    async def get_platform(self, db: AsyncSession) -> EmbeddingConfigRead | None:
        row = await EmbeddingConfigRepository(db).get_platform()
        return _to_read(row) if row else None

    async def get_tenant(
        self, db: AsyncSession, tenant_id: str
    ) -> EmbeddingConfigRead | None:
        row = await EmbeddingConfigRepository(db).get_for_tenant(tenant_id)
        return _to_read(row) if row else None

    async def _upsert(
        self,
        db: AsyncSession,
        payload: EmbeddingConfigUpdate,
        existing: EmbeddingConfig | None,
        *,
        tenant_id: str | None,
    ) -> EmbeddingConfigRead:
        base_url = payload.base_url if payload.base_url is not None else (
            existing.base_url if existing else settings.embedding_base_url
        )
        model = payload.model if payload.model is not None else (
            existing.model if existing else settings.embedding_model
        )

        if existing is not None:
            # Rotate the key only when a new plaintext is supplied; an empty
            # api_key means "keep the stored key".
            if payload.api_key:
                existing.api_key_encrypted = crypto.encrypt(payload.api_key)
                existing.api_key_hint = crypto.mask_api_key(payload.api_key)
            existing.base_url = base_url
            existing.model = model
            row = existing
        else:
            plaintext = payload.api_key or settings.embedding_api_key
            row = EmbeddingConfig(
                tenant_id=tenant_id,
                api_key_encrypted=crypto.encrypt(plaintext),
                api_key_hint=crypto.mask_api_key(plaintext),
                base_url=base_url,
                model=model,
            )
            db.add(row)
        await db.flush()
        await db.commit()
        await db.refresh(row)
        return _to_read(row)

    async def upsert_platform(
        self, db: AsyncSession, payload: EmbeddingConfigUpdate
    ) -> EmbeddingConfigRead:
        existing = await EmbeddingConfigRepository(db).get_platform()
        return await self._upsert(db, payload, existing, tenant_id=None)

    async def upsert_tenant(
        self, db: AsyncSession, tenant_id: str, payload: EmbeddingConfigUpdate
    ) -> EmbeddingConfigRead:
        existing = await EmbeddingConfigRepository(db).get_for_tenant(tenant_id)
        return await self._upsert(db, payload, existing, tenant_id=tenant_id)


embedding_config_service = EmbeddingConfigService()
