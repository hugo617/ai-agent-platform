"""User query/repository helpers for the CRUD endpoints.

``UserRepository`` (in repositories/tenant.py) covers single-row lookups.
This module adds the paginated/filtered list query, soft-delete, statistics,
and the user↔organization link sync — operations specific to user management.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization, UserOrganization
from app.models.tenant import User, UserTenant


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

    Operates within a tenant: the caller passes ``tenant_id`` (resolved from
    the request principal) and every query is scoped to members of that tenant.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _base(self, tenant_id: str):
        """Join users ↔ user_tenants, scoped to the tenant and non-deleted."""
        return (
            select(User)
            .join(UserTenant, UserTenant.user_id == User.id)
            .where(
                UserTenant.tenant_id == tenant_id,
                User.is_deleted.is_(False),
            )
        )

    def _apply(self, stmt, f: UserFilters, tenant_id: str):
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

        col = {
            "created_at": User.created_at,
            "username": User.username,
            "email": User.email,
        }[f.sort_by]
        # Secondary sort by id makes pagination deterministic even when the
        # primary column has ties (e.g. NULL usernames, same created_at).
        direction = col.asc() if f.sort_order == "asc" else col.desc()
        stmt = stmt.order_by(direction, User.id.asc())
        return stmt

    async def list(self, tenant_id: str, f: UserFilters) -> tuple[list[User], int]:
        stmt = self._apply(self._base(tenant_id), f, tenant_id)
        stmt = stmt.limit(f.limit).offset(f.offset)
        result = await self.db.execute(stmt)
        users = list(result.scalars().all())

        count_stmt = select(func.count()).select_from(self._base(tenant_id).subquery())
        count_stmt = self._apply(count_stmt, f, tenant_id)
        # apply() adds ORDER BY which is meaningless for COUNT — strip it.
        count_stmt = count_stmt.order_by(None)
        total = (await self.db.execute(count_stmt)).scalar_one()
        return users, int(total)

    async def get(self, tenant_id: str, user_id: str) -> User | None:
        stmt = self._base(tenant_id).where(User.id == user_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def statistics(self, tenant_id: str) -> dict[str, int]:
        base = self._base(tenant_id)

        def _count(extra):
            stmt = select(func.count()).select_from(base.subquery())
            if extra is not None:
                stmt = stmt.where(extra)
            return stmt.order_by(None)

        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

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
