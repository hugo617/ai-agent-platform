"""ORM models for tenants and users."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # Lifecycle status: active / inactive / locked. MVP default "active".
    status: Mapped[str] = mapped_column(
        String(20), default="active", server_default="active"
    )
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # The platform user who created this tenant (super_admin under the tightened
    # POST policy; nullable for the bootstrap/dev-seed path). Not a hard FK to
    # keep the bootstrap path (where the user row may not exist yet) simple.
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    memberships: Mapped[list["UserTenant"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Tenant {self.id} {self.name}>"


class User(Base):
    """A platform user.

    The primary key mirrors the identity subject: for Logto/OIDC accounts it is
    the JWT ``sub``; for local (username/password) accounts it is a generated
    hex UUID. ``password`` is set only for local accounts (OIDC accounts leave
    it null and authenticate through Logto).
    """

    __tablename__ = "users"
    __table_args__ = (
        # Partial unique indexes scoped to non-deleted rows enforce username /
        # email uniqueness at the DB layer (the application's check-then-insert
        # in UserService.create is racy under concurrency). Mirrored in the
        # migration c1d2e3f4a5b6 -> ce505ae8a1bd. Soft-deleted rows keep their
        # identifiers so they can be reused — every lookup filters
        # is_deleted=False, so this matches the existing reuse semantics.
        Index(
            "uq_users_username_active",
            "username",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index(
            "uq_users_email_active",
            "email",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    username: Mapped[str | None] = mapped_column(String(50), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    real_name: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    avatar: Mapped[str] = mapped_column(String(255), default="/avatars/default.jpg")
    # bcrypt hash; null for OIDC-only accounts.
    password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="active")
    # Platform-level role (null for normal users, "super_admin" for cross-tenant
    # administrators). Separate from the tenant-scoped role on user_tenants.
    platform_role: Mapped[str | None] = mapped_column(
        String(32), nullable=True, default=None
    )

    # ``metadata`` is reserved by SQLAlchemy's DeclarativeBase, so the Python
    # attribute is ``info_json`` while the DB column stays ``metadata``.
    # JSONB on Postgres, plain JSON on SQLite (tests).
    info_json: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"), name="metadata", default=dict
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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

    memberships: Mapped[list["UserTenant"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User {self.id}>"


class UserTenant(Base):
    """Membership of a user in a tenant, with an SCD2 time dimension.

    ``valid_to IS NULL`` marks the *current* role assignment; every other row is
    history supporting "what role did this user hold at time T?". Writes go
    through ``UserTenantRepository.assign_role`` / ``remove_member`` (close old
    row + open new row) — never set ``valid_from``/``valid_to`` directly.
    """

    __tablename__ = "user_tenants"
    __table_args__ = (
        # Partial unique index: at most one *active* membership per
        # (user, tenant). History rows (valid_to set) are exempt, so a member
        # can be re-added after removal. Mirrored PG/SQLite.
        Index(
            "uq_user_tenants_active",
            "user_id",
            "tenant_id",
            unique=True,
            postgresql_where=text("valid_to IS NULL"),
            sqlite_where=text("valid_to IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Role name as used in casbin grouping policy: e.g. "owner", "admin", "member"
    role: Mapped[str] = mapped_column(String(64), nullable=False, default="member")
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="memberships")
    tenant: Mapped["Tenant"] = relationship(back_populates="memberships")

    def __repr__(self) -> str:
        return f"<UserTenant user={self.user_id} tenant={self.tenant_id} role={self.role}>"
