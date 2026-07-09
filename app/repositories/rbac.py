"""Repositories for roles and permissions."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rbac import Permission, Role, RolePermission
from app.repositories.base import BaseRepository

# "Current/active" SCD2 predicate. Every read that should see only the present
# state must carry this; history rows (valid_to set) hold the audit trail.
_ACTIVE = RolePermission.valid_to.is_(None)


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


# TODO: reserved — these back the unbuilt permission-management UI. No endpoint
# uses them yet; keep until /roles/permissions CRUD lands.
class PermissionRepository(BaseRepository[Permission]):
    """Scaffolded for the permission-management UI (not yet wired)."""

    model = Permission

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)


# TODO: reserved — see PermissionRepository above.
class RolePermissionRepository(BaseRepository[RolePermission]):
    """(role, permission) grants with SCD2 write encapsulation.

    Writes go through ``grant`` / ``revoke`` only — they close the prior active
    row and open a new one so history is preserved. Never mutate
    ``valid_from`` / ``valid_to`` from business code.
    """

    model = RolePermission

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    # ----------------------------------------------------------- SCD2 writes

    async def grant(
        self,
        role_id: str,
        permission_id: str,
        tenant_id: str,
        *,
        at: datetime | None = None,
    ) -> RolePermission | None:
        """Grant ``permission_id`` to ``role_id`` (SCD2).

        If an active grant already exists it is returned unchanged (idempotent).
        Otherwise any prior (now-closed) row is left as history and a fresh
        active row is inserted. Returns the active row, or None when no change
        was needed (already granted).
        """
        ts = at or datetime.utcnow()
        current = await self._current(role_id, permission_id, tenant_id)
        if current is not None:
            return current  # already granted → idempotent no-op
        row = RolePermission(
            role_id=role_id,
            permission_id=permission_id,
            tenant_id=tenant_id,
            valid_from=ts,
            valid_to=None,
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def revoke(
        self,
        role_id: str,
        permission_id: str,
        tenant_id: str,
        *,
        at: datetime | None = None,
    ) -> bool:
        """Close the active grant row (history preserved, no physical delete).

        Returns True if a row was closed, False if the grant was not active.
        """
        ts = at or datetime.utcnow()
        current = await self._current(role_id, permission_id, tenant_id)
        if current is None:
            return False
        current.valid_to = ts
        await self.db.flush()
        return True

    # ----------------------------------------------------------- SCD2 reads

    async def current_permissions(
        self, role_id: str, tenant_id: str
    ) -> list[RolePermission]:
        """Active grants for a role (the casbin sync source)."""
        stmt = select(RolePermission).where(
            RolePermission.role_id == role_id,
            RolePermission.tenant_id == tenant_id,
            _ACTIVE,
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def permissions_at(
        self, role_id: str, tenant_id: str, ts: datetime
    ) -> list[RolePermission]:
        """SCD2 point-in-time restore (scenario ii): grants effective at ``ts``."""
        stmt = select(RolePermission).where(
            RolePermission.role_id == role_id,
            RolePermission.tenant_id == tenant_id,
            RolePermission.valid_from <= ts,
            (RolePermission.valid_to.is_(None)) | (RolePermission.valid_to > ts),
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def _current(
        self, role_id: str, permission_id: str, tenant_id: str
    ) -> RolePermission | None:
        stmt = select(RolePermission).where(
            RolePermission.role_id == role_id,
            RolePermission.permission_id == permission_id,
            RolePermission.tenant_id == tenant_id,
            _ACTIVE,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()
