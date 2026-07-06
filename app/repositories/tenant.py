"""Tenant / user repositories."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.tenant import Tenant, User, UserTenant
from app.repositories.base import BaseRepository


class TenantRepository(BaseRepository[Tenant]):
    model = Tenant

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def get_by_id(self, tenant_id: str) -> Tenant | None:
        return await self.db.get(Tenant, tenant_id)


class UserRepository(BaseRepository[User]):
    model = User

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def get_or_create(self, user_id: str, email: str | None = None) -> User:
        user = await self.db.get(User, user_id)
        if user is None:
            user = User(id=user_id, email=email)
            self.db.add(user)
            await self.db.flush()
        return user


class UserTenantRepository(BaseRepository[UserTenant]):
    model = UserTenant

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def get_membership(self, user_id: str, tenant_id: str) -> UserTenant | None:
        stmt = select(UserTenant).where(
            UserTenant.user_id == user_id, UserTenant.tenant_id == tenant_id
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: str) -> list[UserTenant]:
        stmt = select(UserTenant).where(UserTenant.user_id == user_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_for_tenant(self, tenant_id: str) -> list[UserTenant]:
        """Return all memberships in a tenant, eager-loading each user."""
        stmt = (
            select(UserTenant)
            .where(UserTenant.tenant_id == tenant_id)
            .options(selectinload(UserTenant.user))
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_role(self, user_id: str, tenant_id: str) -> str | None:
        membership = await self.get_membership(user_id, tenant_id)
        return membership.role if membership else None
