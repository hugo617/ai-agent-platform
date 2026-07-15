"""Embedding config repository.

Extends ``BaseRepository`` directly (not ``TenantScopedRepository``) because a
row's ``tenant_id`` is *nullable* (NULL = platform-wide); the tenant-scoped
filter would wrongly exclude platform rows. Scope selection is done explicitly
by the dedicated query methods below. Mirrors :class:`LlmConfigRepository`.
"""

from sqlalchemy import select

from app.models.embedding_config import EmbeddingConfig
from app.repositories.base import BaseRepository


class EmbeddingConfigRepository(BaseRepository[EmbeddingConfig]):
    model = EmbeddingConfig

    async def get_platform(self) -> EmbeddingConfig | None:
        """The active platform-wide config row (tenant_id IS NULL)."""
        stmt = select(EmbeddingConfig).where(
            EmbeddingConfig.tenant_id.is_(None), EmbeddingConfig.is_active.is_(True)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_tenant(self, tenant_id: str) -> EmbeddingConfig | None:
        """The active tenant-level config row, if any."""
        stmt = select(EmbeddingConfig).where(
            EmbeddingConfig.tenant_id == tenant_id, EmbeddingConfig.is_active.is_(True)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
