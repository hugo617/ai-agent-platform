"""ORM models for customers (global identity + per-tenant profile).

The customer domain uses a **two-layer model** to support cross-store identity
recognition without breaking tenant isolation:

- ``Customer`` — the *global* identity (phone / ID number keyed). It has NO
  ``tenant_id`` (platform-level), so the same "张三" is recognized across every
  store. ``identity_key`` is globally unique among live rows.
- ``CustomerProfile`` — a *per-store* record with ``tenant_id`` isolation. Each
  store keeps its own private notes/tags/status for a customer. One customer
  may have one profile per store (partial unique index on (customer_id,
  tenant_id) among live rows).

This mirrors the User ↔ UserTenant pattern: identity is global, tenancy is on
the association row. Writes go through ``CustomerService`` which handles the
"create-or-reuse identity, then attach a profile" logic.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class Customer(Base):
    """A global customer identity, recognized across stores.

    Platform-level: no ``tenant_id``. ``identity_key`` (phone / ID number) is
    globally unique among live rows, so the same person maps to exactly one
    Customer regardless of how many stores they visit. Soft-deleted rows are
    exempt from the uniqueness constraint (partial index), mirroring the
    User/Role/Group convention.
    """

    __tablename__ = "customers"
    __table_args__ = (
        # Partial unique index: at most one *live* customer per identity_key.
        # Soft-deleted rows keep their key but are exempt, so keys can be
        # reused after deletion. Mirrored PG/SQLite.
        Index(
            "uq_customers_identity_active",
            "identity_key",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    # Globally unique identifier: phone number, ID card, etc. Two stores
    # creating a customer with the same identity_key reuse the same Customer.
    identity_key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    birthday: Mapped[date | None] = mapped_column(nullable=True)
    avatar: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), index=True
    )
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
        return f"<Customer {self.id} {self.name}>"


class CustomerProfile(Base):
    """A per-store customer record.

    Carries ``tenant_id`` so each store's view is isolated (a store never sees
    another store's notes/tags/status for the same customer). One customer may
    have at most one *live* profile per store (partial unique index); soft-
    deleting a profile allows recreating it later.
    """

    __tablename__ = "customer_profiles"
    __table_args__ = (
        # At most one *live* profile per (customer, tenant). Soft-deleted rows
        # are exempt, so a profile can be recreated after deletion. PG/SQLite.
        Index(
            "uq_profile_customer_tenant_active",
            "customer_id",
            "tenant_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index("idx_customer_profiles_tenant_id", "tenant_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    customer_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Store-private tags. JSONB on Postgres, plain JSON on SQLite (tests).
    tags: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"),
        default=dict,
        server_default=text("'{}'"),
    )
    status: Mapped[str] = mapped_column(
        String(20), default="active", server_default="active"
    )
    last_visit_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("users.id"), nullable=True
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
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
        return f"<CustomerProfile customer={self.customer_id} tenant={self.tenant_id}>"
