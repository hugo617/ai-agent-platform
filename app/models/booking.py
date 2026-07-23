"""ORM model for bookings (tenant-scoped device-usage reservations).

A ``Booking`` reserves a time slot on a tenant-owned ``Device`` for an
optional ``Customer`` (walk-in bookings leave ``customer_id`` NULL — D3).
Unlike most tenant tables, ``bookings`` is **not soft-deleted** (D8): a
cancelled booking keeps its row with ``status='cancelled'`` so the audit
trail survives and the slot is released (cancelled/done/no_show don't
participate in overlap detection). There is intentionally **no** ``is_deleted``
/ ``deleted_at`` column and **no** ``DELETE /bookings/{id}`` endpoint.

``status`` is a 6-state business-state machine (pending / confirmed /
in_service / done / cancelled / no_show). This feature (device-booking)
only ever writes ``pending`` (on create) and transitions pending → cancelled
(via ``POST /bookings/{id}/cancel``). The other four states are CHECK
placeholders for the downstream ``device-poweron`` feature, which owns the
``/start`` / ``/end`` / ``/no-show`` action endpoints. ``confirmed`` is an
unused placeholder (no ``/confirm`` endpoint ships here).

Foreign keys:
- ``tenant_id`` → ``tenants.id`` ``ondelete=CASCADE`` (store gone → bookings gone)
- ``device_id`` → ``devices.id`` ``ondelete=SET NULL`` — keeps the historical
  booking row when a device is (soft-)deleted, mirroring the
  ``devices.customer_id`` convention. The schedule / overlap queries treat a
  NULL ``device_id`` as "no slot".
- ``customer_id`` → ``customers.id`` ``ondelete=SET NULL`` — walk-in bookings
  have NULL here; a deleted customer clears the binding but keeps the booking.
- ``created_by`` → ``users.id`` (no ondelete: matches ``Device`` / ``CustomerProfile``).

Index strategy is query-pattern driven (see plan-device-booking.md §4.4):
- ``idx_bookings_tenant`` — list query (within-store GET /)
- ``idx_bookings_device_schedule`` — (device_id, scheduled_start_at), the
  overlap-detection + schedule-grid hot path
- ``idx_bookings_customer`` — ``GET /me/bookings`` (customer own view, slice 04)
- ``idx_bookings_status`` — filter chips (待确认 / 爽约) + slot-box three-state

There is deliberately **no** partial unique index: overlapping bookings are a
runtime business rule (only active states conflict, and the rule is enforced
in ``BookingService._assert_no_overlap``), not a static column invariant.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    # Forward declarations for relationship type hints. Never imported at
    # runtime — SQLAlchemy resolves the string class names through its
    # declarative registry at mapper-configure time. Under TYPE_CHECKING so
    # static checkers (ruff F821) see the names without an import cycle
    # (customer/device/tenant ↔ booking).
    from app.models.customer import Customer
    from app.models.device import Device
    from app.models.tenant import Tenant

from app.core.database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class Booking(Base):
    """A device-usage reservation owned by a store.

    Lifecycle (this feature): ``pending`` → ``cancelled``. The remaining
    states (``confirmed`` / ``in_service`` / ``done`` / ``no_show``) are
    written by ``device-poweron``'s action endpoints — the columns they need
    (``started_at`` / ``ended_at`` / ``feedback``) are created here, once, so
    ``device-poweron`` ships without a schema migration (D7).
    """

    __tablename__ = "bookings"
    __table_args__ = (
        # 6-state machine. Not a PG ENUM (adding a state would need a dedicated
        # migration — overkill for a status flag). SQLite + PG both accept the
        # same CheckConstraint text. Mirrors the devices.status pattern.
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'in_service', 'done', "
            "'cancelled', 'no_show')",
            name="ck_bookings_status_valid",
        ),
        Index("idx_bookings_tenant", "tenant_id"),
        Index("idx_bookings_device_schedule", "device_id", "scheduled_start_at"),
        Index("idx_bookings_customer", "customer_id"),
        Index("idx_bookings_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    device_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True,
    )
    customer_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("users.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending"
    )

    # ---- time fields, built once (D7) ----
    # scheduled_* are written by this feature (the reservation window).
    scheduled_start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    scheduled_end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # started_at / ended_at / feedback are nullable placeholders owned by
    # device-poweron's /start / /end actions. This feature never writes them;
    # the create/update schemas intentionally don't expose them (status-guard
    # rule — see BookingCreate / BookingUpdate docstrings).
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    feedback: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ---- relationships (read-only navigation; writes go through FK columns) ----
    # Declared so the HQ panorama repository (slice 03) can ``selectinload``
    # them and dodge the async-session ``MissingGreenlet`` a lazy attribute
    # access would raise. Intentionally NOT ``back_populates`` — the target
    # models don't need a reverse collection (mirrors the Device convention).
    tenant: Mapped["Tenant"] = relationship(
        primaryjoin="Booking.tenant_id == Tenant.id", foreign_keys=[tenant_id]
    )
    device: Mapped["Device | None"] = relationship(
        primaryjoin="Booking.device_id == Device.id", foreign_keys=[device_id]
    )
    customer: Mapped["Customer | None"] = relationship(
        primaryjoin="Booking.customer_id == Customer.id", foreign_keys=[customer_id]
    )

    def __repr__(self) -> str:
        return (
            f"<Booking {self.id} tenant={self.tenant_id} "
            f"device={self.device_id} status={self.status}>"
        )


# Re-export for callers that need it.
__all__ = ["Booking"]
