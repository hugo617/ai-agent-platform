"""LLM config repository.

Unlike tenant-scoped repos this extends ``BaseRepository`` directly: a row's
``tenant_id`` is *nullable* (NULL = platform-wide), so the ``get_for_tenant``
filter would wrongly exclude platform rows. Scope selection (platform vs
tenant) is done explicitly by the dedicated query methods below.
"""

from sqlalchemy import select

from app.models.llm_config import LlmConfig
from app.repositories.base import BaseRepository


class LlmConfigRepository(BaseRepository[LlmConfig]):
    model = LlmConfig

    async def get_platform(self) -> LlmConfig | None:
        """The active platform-wide config row (tenant_id IS NULL)."""
        stmt = select(LlmConfig).where(
            LlmConfig.tenant_id.is_(None), LlmConfig.is_active.is_(True)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_tenant(self, tenant_id: str) -> LlmConfig | None:
        """The active tenant-level config row, if any."""
        stmt = select(LlmConfig).where(
            LlmConfig.tenant_id == tenant_id, LlmConfig.is_active.is_(True)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
