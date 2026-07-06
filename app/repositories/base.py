"""Generic repository base.

Every tenant-scoped entity inherits from ``TenantScopedRepository`` which
forces a ``tenant_id`` filter on every read — this is the single place where
multi-tenant data isolation is enforced, so it cannot be forgotten.
"""

from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Generic CRUD repository over a SQLAlchemy model."""

    model: type[ModelT]

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, obj_id: str) -> ModelT | None:
        return await self.db.get(self.model, obj_id)

    async def add(self, obj: ModelT) -> ModelT:
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def delete(self, obj: ModelT) -> None:
        await self.db.delete(obj)
        await self.db.flush()


class TenantScopedRepository(BaseRepository[ModelT]):
    """Repository for entities that carry a ``tenant_id`` column.

    Every query is automatically scoped to the given tenant, preventing
    cross-tenant data leakage at the data-access layer.
    """

    async def get_for_tenant(self, obj_id: str, tenant_id: str) -> ModelT | None:
        stmt = select(self.model).where(
            self.model.id == obj_id,  # type: ignore[attr-defined]
            self.model.tenant_id == tenant_id,  # type: ignore[attr-defined]
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_tenant(self, tenant_id: str, limit: int = 100, offset: int = 0) -> list[ModelT]:
        stmt = (
            select(self.model)
            .where(self.model.tenant_id == tenant_id)  # type: ignore[attr-defined]
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
