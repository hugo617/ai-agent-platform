"""Repository for the organization tree."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.repositories.base import BaseRepository


class OrganizationRepository(BaseRepository[Organization]):
    model = Organization

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def list_for_tenant(self, tenant_id: str) -> list[Organization]:
        stmt = (
            select(Organization)
            .where(Organization.tenant_id == tenant_id)
            .order_by(Organization.sort_order, Organization.created_at)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_for_tenant(
        self, tenant_id: str, org_id: str
    ) -> Organization | None:
        stmt = select(Organization).where(
            Organization.id == org_id, Organization.tenant_id == tenant_id
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()
