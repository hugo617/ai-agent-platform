"""ORM models for roles and permissions (RBAC).

Two layers coexist (see the RBAC「宪法」in ``permission_service``):

- ``roles`` / ``permissions`` — display + admin layer. A tenant's seeded
  ``Role`` rows (owner/admin/member) mirror the role names used in casbin's
  grouping policy, and the role dropdown on the user form reads from here.
- ``role_permissions`` — **角色权限历史还原的唯一数据源(SCD2)**。它的当前态
  (``valid_to IS NULL``)同步给 casbin;历史行支持「任意时间点还原某角色的权限集」。
  casbin 永远只回答「现在能不能做」,历史回溯看这张表。

改角色权限集必须走 ``RolePermissionRepository.grant/revoke``(关旧行 + 插新行),
业务代码绝不直接操作 ``valid_from`` / ``valid_to``。
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_roles_tenant_code"),
        UniqueConstraint("tenant_id", "name", name="uq_roles_tenant_name"),
        Index("idx_roles_tenant_id", "tenant_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    tenant_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sort_order: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(20), default="active")
    # Row-level data scope for the role (权限重构系列 3/4). Four levels:
    #   "all"     — platform-wide, no filter (only super_admin/hq_staff via bypass)
    #   "tenant"  — this tenant's rows (default; owner/admin/member)
    #   "group"   — rows in all tenants belonging to the user's Group(s)
    #   "self"    — only rows created by the user
    # Enforced at the Repository layer via DataScopeService (app/services/data_scope).
    data_scope: Mapped[str] = mapped_column(String(20), default="tenant")
    created_by: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("users.id"), nullable=True
    )
    updated_by: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Role {self.code} tenant={self.tenant_id}>"


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_permissions_tenant_code"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    tenant_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(20), default="api")
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sort_order: Mapped[int] = mapped_column(default=0)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Permission {self.code}>"


class RolePermission(Base):
    """A (role, permission) grant with a SCD2 time dimension.

    ``valid_to IS NULL`` marks the current/active grant; every other row is
    history supporting "what permissions did this role have at time T?". Writes
    go through ``RolePermissionRepository.grant/revoke`` (close old row + open
    new row) — never set ``valid_from``/``valid_to`` directly.
    """

    __tablename__ = "role_permissions"
    __table_args__ = (
        # Partial unique index: at most one *active* grant per
        # (tenant, role, permission). History rows (valid_to set) are exempt.
        # Mirrored PG/SQLite — see migration for the dual-dialect form.
        Index(
            "uq_role_permissions_active",
            "tenant_id",
            "role_id",
            "permission_id",
            unique=True,
            postgresql_where=text("valid_to IS NULL"),
            sqlite_where=text("valid_to IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    role_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    permission_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False
    )
    # NOTE: tenant_id is a deliberate *soft reference* (no ForeignKey). It is a
    # denormalised business key carried for tenant-scoped queries; the tenant
    # link is already enforced transitively via role_id → roles.tenant_id (with
    # ondelete CASCADE). Adding an FK here would create a competing cascade path
    # against role_id, so it is registered as a known intentional exception.
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
