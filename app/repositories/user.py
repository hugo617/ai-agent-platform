"""User query/repository helpers for the CRUD endpoints.

``UserRepository`` (in repositories/tenant.py) covers single-row lookups.
This module adds the paginated/filtered list query, soft-delete, statistics,
and the user↔organization link sync — operations specific to user management.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization, UserOrganization
from app.models.tenant import Tenant, User, UserTenant


class UserFilters:
    """Parsed query-string filters for the user list endpoint."""

    def __init__(
        self,
        *,
        search: str | None = None,
        status: str | None = None,
        role: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        page: int = 1,
        limit: int = 10,
    ) -> None:
        self.search = (search or None) and search.strip() or None
        self.status = status if status and status != "all" else None
        self.role = role if role and role != "all" else None
        self.sort_by = sort_by if sort_by in {"created_at", "username", "email"} else "created_at"
        self.sort_order = "asc" if sort_order.lower() == "asc" else "desc"
        self.page = max(1, page)
        self.limit = min(100, max(1, limit))

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


class UserListRepository:
    """Read-side queries for the user list + statistics.

    Operates within a tenant by default. When ``super_admin=True``, returns
    users across all tenants with their current tenant membership info.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _base(self, tenant_id: str):
        """Join users ↔ user_tenants, scoped to the tenant and non-deleted.

        Filters to the *current* membership row (``valid_to IS NULL``) so SCD2
        history rows (a member's prior role assignments) don't double-count a
        user after a role change. This is the read-side consequence of the SCD2
        write path — see permission_service.py's RBAC「宪法」.
        """
        return (
            select(User)
            .join(UserTenant, UserTenant.user_id == User.id)
            .where(
                UserTenant.tenant_id == tenant_id,
                UserTenant.valid_to.is_(None),
                User.is_deleted.is_(False),
            )
        )

    def _base_all(self):
        """All non-deleted users with their current tenant (LEFT JOIN).

        Used by super admin to see users across all tenants. Users without an
        active membership still appear (tenant fields will be None).
        """
        return (
            select(User, UserTenant.tenant_id, Tenant.name.label("tenant_name"))
            .outerjoin(UserTenant, (UserTenant.user_id == User.id) & UserTenant.valid_to.is_(None))
            .outerjoin(Tenant, Tenant.id == UserTenant.tenant_id)
            .where(User.is_deleted.is_(False))
        )

    def _apply_filters(self, stmt, f: UserFilters):
        """Apply WHERE filters (search / status / role) to a statement."""
        if f.search:
            like = f"%{f.search}%"
            stmt = stmt.where(
                or_(
                    User.username.ilike(like),
                    User.email.ilike(like),
                    User.real_name.ilike(like),
                    User.phone.ilike(like),
                )
            )
        if f.status:
            stmt = stmt.where(User.status == f.status)
        if f.role:
            stmt = stmt.where(UserTenant.role == f.role)
        return stmt

    def _apply_sort(self, stmt, f: UserFilters):
        col = {
            "created_at": User.created_at,
            "username": User.username,
            "email": User.email,
        }[f.sort_by]
        # Secondary sort by id makes pagination deterministic even when the
        # primary column has ties (e.g. NULL usernames, same created_at).
        direction = col.asc() if f.sort_order == "asc" else col.desc()
        return stmt.order_by(direction, User.id.asc())

    async def list(
        self, tenant_id: str, f: UserFilters, super_admin: bool = False
    ) -> tuple[list[User], int]:
        """List users. When ``super_admin`` is True, returns all users across tenants."""
        if super_admin:
            return await self._list_all(f)
        stmt = self._apply_sort(self._apply_filters(self._base(tenant_id), f), f)
        stmt = stmt.limit(f.limit).offset(f.offset)
        result = await self.db.execute(stmt)
        users = list(result.scalars().all())

        # Filters must be applied INSIDE the subquery (on User) — wrapping them
        # on the outer count() references a free-standing users table and yields
        # a cartesian product (total >> actual rows).
        counted = self._apply_filters(self._base(tenant_id), f).subquery()
        count_stmt = select(func.count()).select_from(counted)
        total = (await self.db.execute(count_stmt)).scalar_one()
        return users, int(total)

    async def _list_all(self, f: UserFilters) -> tuple[list[User], int]:
        """List all non-deleted users across tenants with their current membership."""
        base = self._base_all()
        stmt = self._apply_sort(self._apply_filters(base, f), f)
        stmt = stmt.limit(f.limit).offset(f.offset)
        result = await self.db.execute(stmt)
        rows = result.all()
        users = [row.User for row in rows]

        # Same cartesian-product guard as list(): apply filters inside the subquery.
        counted = self._apply_filters(base, f).subquery()
        count_stmt = select(func.count()).select_from(counted)
        total = (await self.db.execute(count_stmt)).scalar_one()
        return users, int(total)

    async def get(self, tenant_id: str, user_id: str) -> User | None:
        stmt = self._base(tenant_id).where(User.id == user_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def statistics(
        self, tenant_id: str, *, super_admin: bool = False
    ) -> dict[str, int]:
        # Super admin counts across ALL tenants (just the users table — no join,
        # so multi-tenant members don't double-count); tenant admins count only
        # their own via the membership join. Must stay consistent with list()'s
        # total so the stat cards and pagination never disagree.

        def _base():
            # A fresh base each call: extra filters must be applied INSIDE the
            # subquery (on User), not on the outer count() — otherwise the outer
            # where references a free-standing users table and triggers a
            # cartesian product (active > total).
            if super_admin:
                return select(User).where(User.is_deleted.is_(False))
            return self._base(tenant_id)

        def _count(extra):
            stmt = _base()
            if extra is not None:
                stmt = stmt.where(extra)
            return select(func.count()).select_from(stmt.subquery()).order_by(None)

        thirty_days_ago = datetime.now(UTC) - timedelta(days=30)
        month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        total = (await self.db.execute(_count(None))).scalar_one()
        active = (await self.db.execute(_count(User.status == "active"))).scalar_one()
        inactive = (await self.db.execute(_count(User.status == "inactive"))).scalar_one()
        locked = (await self.db.execute(_count(User.status == "locked"))).scalar_one()
        recent = (
            await self.db.execute(_count(User.last_login_at >= thirty_days_ago))
        ).scalar_one()
        new_month = (
            await self.db.execute(_count(User.created_at >= month_start))
        ).scalar_one()
        return {
            "total": int(total),
            "active": int(active),
            "inactive": int(inactive),
            "locked": int(locked),
            "recent_logins": int(recent),
            "new_this_month": int(new_month),
        }

    async def batch_tenant_info(
        self, user_ids: list[str]
    ) -> dict[str, tuple[str | None, str | None]]:
        """Return ``{user_id: (tenant_id, tenant_name)}`` for current memberships."""
        if not user_ids:
            return {}
        stmt = (
            select(UserTenant.user_id, UserTenant.tenant_id, Tenant.name)
            .join(Tenant, Tenant.id == UserTenant.tenant_id)
            .where(
                UserTenant.user_id.in_(user_ids),
                UserTenant.valid_to.is_(None),
            )
        )
        result = await self.db.execute(stmt)
        return {row.user_id: (row.tenant_id, row.name) for row in result}

    async def list_organizations(self, user_id: str) -> list[Organization]:
        stmt = (
            select(Organization)
            .join(UserOrganization, UserOrganization.organization_id == Organization.id)
            .where(UserOrganization.user_id == user_id)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def sync_organizations(
        self, user_id: str, organization_ids: list[str]
    ) -> None:
        """Replace the user's org memberships with the given list."""
        existing = await self.db.execute(
            select(UserOrganization).where(UserOrganization.user_id == user_id)
        )
        for row in existing.scalars().all():
            await self.db.delete(row)
        for idx, org_id in enumerate(organization_ids):
            self.db.add(
                UserOrganization(
                    user_id=user_id,
                    organization_id=org_id,
                    is_main=(idx == 0),
                )
            )
        await self.db.flush()


def serialize_user(
    user: User,
    *,
    role: str | None = None,
    role_id: str | None = None,
    role_name: str | None = None,
    role_code: str | None = None,
    organizations: list[Organization] | None = None,
) -> dict[str, Any]:
    """Flatten a User ORM row + its role/orgs into a UserRead-shaped dict.

    The role is passed in (resolved separately) because it lives on
    ``user_tenants``, not on the user row itself.
    """
    role_brief = None
    if role or role_code:
        role_brief = {
            "id": role_id or "",
            "name": role_name or (role or ""),
            "code": role_code or (role or ""),
        }
    orgs = [
        {"id": o.id, "name": o.name, "code": o.code}
        for o in (organizations or [])
    ]
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "display_name": user.display_name,
        "real_name": user.real_name,
        "phone": user.phone,
        "avatar": user.avatar,
        "status": user.status,
        "role": role_brief,
        "organizations": orgs,
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }
