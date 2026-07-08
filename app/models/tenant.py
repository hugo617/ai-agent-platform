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
    """Association table: a user can belong to multiple tenants with a role."""

    __tablename__ = "user_tenants"

    user_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # Role name as used in casbin grouping policy: e.g. "owner", "admin", "member"
    role: Mapped[str] = mapped_column(String(64), nullable=False, default="member")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="memberships")
    tenant: Mapped["Tenant"] = relationship(back_populates="memberships")

    def __repr__(self) -> str:
        return f"<UserTenant user={self.user_id} tenant={self.tenant_id} role={self.role}>"
