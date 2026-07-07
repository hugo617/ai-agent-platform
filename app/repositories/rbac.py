"""Repositories for roles and permissions."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rbac import Permission, Role, RolePermission
from app.repositories.base import BaseRepository


class RoleRepository(BaseRepository[Role]):
    model = Role

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def list_for_tenant(self, tenant_id: str) -> list[Role]:
        stmt = (
            select(Role)
            .where(Role.tenant_id == tenant_id, Role.is_deleted.is_(False))
            .order_by(Role.sort_order, Role.created_at)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_for_tenant(self, tenant_id: str, role_id: str) -> Role | None:
        stmt = select(Role).where(
            Role.id == role_id,
            Role.tenant_id == tenant_id,
            Role.is_deleted.is_(False),
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_by_code(self, tenant_id: str, code: str) -> Role | None:
        stmt = select(Role).where(
            Role.tenant_id == tenant_id,
            Role.code == code,
            Role.is_deleted.is_(False),
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()


class PermissionRepository(BaseRepository[Permission]):
    """Scaffolded for the permission-management UI (not yet wired)."""

    model = Permission

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)


class RolePermissionRepository(BaseRepository[RolePermission]):
    """Scaffolded for the permission-management UI (not yet wired)."""
    model = RolePermission

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)
