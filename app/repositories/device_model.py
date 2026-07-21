"""Repository for DeviceModel.

DeviceModel is a platform-level entity (no ``tenant_id``), so
``DeviceModelRepository`` extends ``BaseRepository`` directly — NOT
``TenantScopedRepository``. Reads filter ``is_deleted=False`` manually
(soft-delete convention shared with Group/User/Role).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.models.device_model import DeviceModel
from app.repositories.base import BaseRepository


class DeviceModelRepository(BaseRepository[DeviceModel]):
    """Platform-level CRUD over device_models (cross-tenant, soft-deleted)."""

    model = DeviceModel

    def __init__(self, db: AsyncSession) -> None:
        # BaseRepository.__init__ only stores self.db; call it for consistency.
        super().__init__(db)

    async def get(self, model_id: str) -> DeviceModel | None:
        """Fetch a live (non-deleted) device model by id."""
        stmt = select(DeviceModel).where(
            DeviceModel.id == model_id, DeviceModel.is_deleted.is_(False)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self) -> list[DeviceModel]:
        """All live device models, newest first."""
        stmt = (
            select(DeviceModel)
            .where(DeviceModel.is_deleted.is_(False))
            .order_by(DeviceModel.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_name(self, name: str) -> DeviceModel | None:
        """Live device model by name (uniqueness check on create/update)."""
        stmt = select(DeviceModel).where(
            DeviceModel.name == name, DeviceModel.is_deleted.is_(False)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()


# Re-export Base for type hints in callers that need it.
__all__ = ["Base", "DeviceModelRepository"]
