"""ORM models for groups (cross-tenant business entities).

A ``Group`` is a platform-level entity that represents a business organisation
— typically a chain operating across multiple stores/tenants, or a single
store. Unlike the old tenant-scoped ``Organization`` (an internal department
tree), a Group has **no tenant_id**: it sits above tenants and ties several of
them together via the ``GroupTenant`` association table.

Permissions are platform-level: writes are guarded by ``require_super_admin()``
(only the platform super admin can reshape the org tree), while reads are open
to any authenticated user — the service splits super_admin (see every Group)
from tenant users (only see Groups their tenant belongs to).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class Group(Base):
    """A cross-tenant business group (chain HQ or single store).

    Platform-level: no ``tenant_id``. Stores are attached via ``GroupTenant``.
    Soft-deleted (``is_deleted`` + partial unique index on ``code`` so a deleted
    group's code can be reused, mirroring the User/Role convention).
    """

    __tablename__ = "groups"
    __table_args__ = (
        # Partial unique index: at most one *live* group per code. Soft-deleted
        # rows keep their code but are exempt, so codes can be reused after
        # deletion. Mirrored PG/SQLite — see User.uq_users_username_active.
        Index(
            "uq_groups_code_active",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Business code (e.g. chain identifier). Nullable: single-store groups may
    # not have one. Uniqueness is enforced only among live rows (see above).
    code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    sort_order: Mapped[int] = mapped_column(default=0)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Group {self.id} {self.name}>"


class GroupTenant(Base):
    """Many-to-many: which tenants (stores) belong to a Group.

    Joining/unjoining a store = insert/delete a row here (no soft delete — the
    relation either exists or it doesn't). ``UniqueConstraint`` therefore
    suffices for "a store is attached to a group at most once".
    """

    __tablename__ = "group_tenants"
    __table_args__ = (
        UniqueConstraint("group_id", "tenant_id", name="uq_group_tenant"),
        Index("idx_group_tenants_tenant_id", "tenant_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    group_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<GroupTenant group={self.group_id} tenant={self.tenant_id}>"
