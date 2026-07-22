"""ORM model for devices (tenant-scoped device instances).

A ``Device`` is a tenant-scoped entity: a concrete device instance owned by one
store (``tenant_id``), instantiated from a platform-level ``DeviceModel``
(``model_id``). Unlike ``DeviceModel`` (the catalogue), ``Device`` carries the
serial number, the operational state (``status``) and an optional customer
binding (``customer_id``).

Permission model mirrors other tenant-scoped entities (customers / agents):
``owner`` and ``admin`` can write; ``member`` is read-only; ``super_admin`` and
``hq_staff`` are cross-tenant viewers (HQ panorama — slice 03 will wire this
up). Slice 01 only does the within-store CRUD path behind router-level
``require_permission("devices", act)``.

Foreign keys:
- ``tenant_id`` → ``tenants.id`` ``ondelete=CASCADE`` (store gone → devices gone)
- ``model_id`` → ``device_models.id`` ``ondelete=RESTRICT`` — a dead-bolt that
  never fires in the current code path (``DeviceModelService.delete`` is soft-
  delete only). The *real* guard is ``DeviceService._assert_model_live``: it
  refuses to create or re-point a device at a soft-deleted/nonexistent model.
  RESTRICT stays as a future-proof safety net if a hard-delete endpoint is
  ever added.
- ``customer_id`` → ``customers.id`` ``ondelete=SET NULL`` — also a dead-bolt:
  ``Customer`` is soft-delete-only today, so the FK never fires. Kept so a
  future Customer hard-delete clears the binding instead of taking the device
  down with it.
- ``created_by`` → ``users.id`` (no ondelete: stays like ``CustomerProfile``).

Soft-deleted via ``is_deleted`` + a partial unique index on
``(tenant_id, serial_number)`` so a deleted device's serial can be reused
within the same tenant. Mirrored PG/SQLite (otherwise alembic check drifts).
``status`` is a 3-state business-state (active / maintenance / retired), NOT
an IoT online/offline signal — see the feature notes in ``feature_list.json``.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    # Forward declarations for the relationship type hints below. These are
    # never imported at runtime — SQLAlchemy resolves the string class names
    # through its declarative registry at mapper-configure time. Kept under
    # TYPE_CHECKING so static checkers (ruff F821) see the names without
    # creating an import cycle (customer/tenant/device_model ↔ device).
    from app.models.customer import Customer
    from app.models.device_model import DeviceModel
    from app.models.tenant import Tenant

from app.core.database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class Device(Base):
    """A device instance owned by a store.

    ``status`` is the *management* state of the device (active/maintenance/
    retired). It is NOT the IoT online/offline signal — "is this device
    currently in use" is derived from bookings (``WHERE device_id=? AND
    status='in_service'``), not from ``devices.status``.
    """

    __tablename__ = "devices"
    __table_args__ = (
        # At most one *live* device per (tenant, serial_number). Soft-deleted
        # rows keep their serial but are exempt, so a serial can be reused
        # after the prior device is deleted. Mirrored PG/SQLite.
        Index(
            "uq_devices_tenant_serial_active",
            "tenant_id",
            "serial_number",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index("idx_devices_tenant_id", "tenant_id"),
        # 3-state business-state. Not a PG ENUM (adding a value would need a
        # dedicated migration — overkill for a 3-state flag). SQLite + PG both
        # accept the same CheckConstraint text.
        CheckConstraint(
            "status IN ('active', 'maintenance', 'retired')",
            name="ck_devices_status_valid",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    model_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("device_models.id", ondelete="RESTRICT"),
        nullable=False,
    )
    serial_number: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="active", server_default="active"
    )
    customer_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("users.id"), nullable=True
    )
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

    # ---- relationships (read-only navigation; writes go through FK columns) ----
    # Declared so the HQ panorama repository can ``selectinload`` them and dodge
    # the async-session ``MissingGreenlet`` that a lazy attribute access would
    # raise. These are intentionally NOT ``back_populates`` — the target models
    # don't need a reverse collection, and adding one would couple the customer
    # / tenant / device_model domains to devices for no reader's benefit.
    tenant: Mapped["Tenant"] = relationship(
        primaryjoin="Device.tenant_id == Tenant.id", foreign_keys=[tenant_id]
    )
    model: Mapped["DeviceModel"] = relationship(
        primaryjoin="Device.model_id == DeviceModel.id", foreign_keys=[model_id]
    )
    customer: Mapped["Customer | None"] = relationship(
        primaryjoin="Device.customer_id == Customer.id", foreign_keys=[customer_id]
    )

    def __repr__(self) -> str:
        return f"<Device {self.id} tenant={self.tenant_id} serial={self.serial_number}>"


# Re-export for callers that need it.
__all__ = ["Device"]
