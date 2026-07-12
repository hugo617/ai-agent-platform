"""Tenant / user repositories."""

from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.tenant import Tenant, User, UserTenant
from app.repositories.base import BaseRepository

# Predicate matching the "current/active" SCD2 row. Every read that should see
# only the present state must carry this; history rows (valid_to set) hold the
# audit trail. Kept as a module-level expression so it cannot drift.
_ACTIVE = UserTenant.valid_to.is_(None)


class TenantRepository(BaseRepository[Tenant]):
    model = Tenant

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def get_by_id(self, tenant_id: str) -> Tenant | None:
        return await self.db.get(Tenant, tenant_id)

    # ----------------------------------------------- platform-level reads
    # Used by the super_admin endpoints (GET /tenants/all, GET /tenants/{id}).
    # member_count is a runtime aggregate (COUNT active user_tenants rows) — it
    # is NOT a persisted column, so callers pair each Tenant with its count.

    async def list_all_with_member_count(self) -> list[tuple[Tenant, int]]:
        """All tenants, each paired with its active member count.

        LEFT JOIN so tenants with zero members still appear (count 0). Ordered
        by created_at desc so the newest stores surface first.
        """
        stmt = (
            select(
                Tenant,
                func.count(UserTenant.id).label("member_count"),
            )
            .outerjoin(UserTenant, (UserTenant.tenant_id == Tenant.id) & _ACTIVE)
            .group_by(Tenant.id)
            .order_by(Tenant.created_at.desc())
        )
        rows = (await self.db.execute(stmt)).all()
        return [(tenant, int(count)) for tenant, count in rows]

    async def get_detail_with_member_count(
        self, tenant_id: str
    ) -> tuple[Tenant, int] | None:
        """Single tenant with its active member count, or None if not found."""
        stmt = (
            select(
                Tenant,
                func.count(UserTenant.id).label("member_count"),
            )
            .outerjoin(UserTenant, (UserTenant.tenant_id == Tenant.id) & _ACTIVE)
            .where(Tenant.id == tenant_id)
            .group_by(Tenant.id)
        )
        row = (await self.db.execute(stmt)).one_or_none()
        if row is None:
            return None
        tenant, count = row
        return tenant, int(count)


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

    async def get_by_username(self, username: str) -> User | None:
        stmt = select(User).where(
            User.username == username, User.is_deleted.is_(False)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(
            User.email == email, User.is_deleted.is_(False)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_login_identifier(self, identifier: str) -> User | None:
        """Look up by username OR email (used by the login endpoint)."""
        stmt = select(User).where(
            or_(User.username == identifier, User.email == identifier),
            User.is_deleted.is_(False),
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_last_login(self, user_id: str) -> None:
        user = await self.db.get(User, user_id)
        if user is not None:
            user.last_login_at = datetime.now(UTC)
            await self.db.flush()


class UserTenantRepository(BaseRepository[UserTenant]):
    """Membership repository with SCD2 write encapsulation.

    Writes go through ``assign_role`` / ``remove_member`` only — they close the
    prior active row and open a new one so history is preserved. Never mutate
    ``valid_from`` / ``valid_to`` from business code.
    """

    model = UserTenant

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    # ----------------------------------------------------------- SCD2 writes

    async def assign_role(
        self,
        user_id: str,
        tenant_id: str,
        role: str,
        *,
        at: datetime | None = None,
    ) -> UserTenant:
        """Set ``user_id``'s role in ``tenant_id`` to ``role`` (SCD2).

        Closes any currently-active row for this (user, tenant) by setting
        ``valid_to = at``, then inserts a fresh active row. Idempotent: if the
        active role already equals ``role`` the existing row is reused.

        ``at`` defaults to ``utcnow()``; tests pass an explicit value so
        time-point assertions are deterministic.
        """
        ts = at or datetime.now(UTC)
        current = await self.current_role(user_id, tenant_id)
        if current is not None and current.role == role:
            return current  # no change → no history churn
        if current is not None:
            current.valid_to = ts
            await self.db.flush()
        row = UserTenant(
            user_id=user_id,
            tenant_id=tenant_id,
            role=role,
            valid_from=ts,
            valid_to=None,
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def remove_member(
        self,
        user_id: str,
        tenant_id: str,
        *,
        at: datetime | None = None,
    ) -> bool:
        """Close the active membership row (history preserved, no physical delete).

        Returns True if a row was closed, False if there was no active member.
        """
        ts = at or datetime.now(UTC)
        current = await self.current_role(user_id, tenant_id)
        if current is None:
            return False
        current.valid_to = ts
        await self.db.flush()
        return True

    # ----------------------------------------------------------- SCD2 reads

    async def current_role(
        self, user_id: str, tenant_id: str
    ) -> UserTenant | None:
        """The *active* membership row, or None if not currently a member."""
        stmt = select(UserTenant).where(
            UserTenant.user_id == user_id,
            UserTenant.tenant_id == tenant_id,
            _ACTIVE,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def member_role_at(
        self, user_id: str, tenant_id: str, ts: datetime
    ) -> UserTenant | None:
        """SCD2 point-in-time restore (scenario i): role held at ``ts``."""
        stmt = select(UserTenant).where(
            UserTenant.user_id == user_id,
            UserTenant.tenant_id == tenant_id,
            UserTenant.valid_from <= ts,
            (UserTenant.valid_to.is_(None)) | (UserTenant.valid_to > ts),
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def current_members(self, tenant_id: str) -> list[UserTenant]:
        """Active memberships in a tenant, eager-loading each user (for the
        member directory). Replaces the old ``list_for_tenant`` semantics."""
        stmt = (
            select(UserTenant)
            .join(User, UserTenant.user_id == User.id)
            .where(
                UserTenant.tenant_id == tenant_id,
                _ACTIVE,
                User.is_deleted.is_(False),
            )
            .options(selectinload(UserTenant.user))
        )
        return list((await self.db.execute(stmt)).scalars().all())

    # -------------------------------------------- backward-compat shims
    # Kept thin (current-state only) so existing callers compile; service-layer
    # migration (step 8) routes them through the SCD2 methods above.

    async def get_membership(self, user_id: str, tenant_id: str) -> UserTenant | None:
        """Active membership (alias of ``current_role``)."""
        return await self.current_role(user_id, tenant_id)

    async def list_for_user(self, user_id: str) -> list[UserTenant]:
        """Active memberships for a user across tenants."""
        stmt = select(UserTenant).where(UserTenant.user_id == user_id, _ACTIVE)
        return list((await self.db.execute(stmt)).scalars().all())

    async def list_for_tenant(self, tenant_id: str) -> list[UserTenant]:
        """Active memberships in a tenant (alias of ``current_members``)."""
        return await self.current_members(tenant_id)
