"""Pydantic schemas for booking DTOs (slice 01 — within-store CRUD).

State-guard rule (plan §4.5): ``status`` / ``started_at`` / ``ended_at`` /
``feedback`` are **never** writable through ``POST`` / ``PUT``. They are owned
by the booking's lifecycle action endpoints:

- ``status`` transitions only via ``POST /bookings/{id}/cancel``
  (pending → cancelled) in this feature. The downstream ``device-poweron``
  feature owns ``/start`` (→ in_service) / ``/end`` (→ done) / ``/no-show``
  (→ no_show).
- ``started_at`` / ``ended_at`` / ``feedback`` are written by device-poweron's
  ``/start`` / ``/end`` only.

So ``BookingCreate`` / ``BookingUpdate`` deliberately omit those fields — a
client sending ``status: "done"`` on create is silently ignored (Pydantic
drops unknown keys by default), and the DB CHECK constraint is the backstop.
This is the same "schema is the front guard, DB is defence-in-depth" pattern
as ``devices.status``.

``BookingStatus`` is a Literal (not an Enum) so the 422-on-bad-value behaviour
falls out of Pydantic for free and the CHECK constraint is a backstop.

The HQ panorama shape (``BookingHqRead``, slice 03) extends ``BookingRead``
with three cross-tenant display fields (``tenant_name`` / ``device_name`` /
``customer_name``) so a super_admin / hq_staff viewer can see which store,
which device, and which customer a booking belongs to without N client-side
lookups — mirrors the ``DeviceHqRead`` convention.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

BookingStatus = Literal[
    "pending",
    "confirmed",
    "in_service",
    "done",
    "cancelled",
    "no_show",
]


class BookingBase(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=32)
    # Walk-in bookings (D3): customer_id may be None.
    customer_id: str | None = Field(default=None, max_length=32)
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    notes: str | None = Field(default=None, max_length=2000)


class BookingCreate(BookingBase):
    """POST /bookings/ body.

    Intentionally carries NO ``status`` / ``started_at`` / ``ended_at`` /
    ``feedback``: new bookings always start ``pending`` and the lifecycle
    fields are owned by device-poweron's action endpoints. A client that
    sends those keys has them silently dropped (Pydantic default) — the
    status-guard rule.

    The ``scheduled_end_at > scheduled_start_at`` invariant is NOT enforced
    here via a ``model_validator``: a hand-rolled validator raising
    ``ValueError`` embeds the raw exception object in the error's ``ctx``,
    which FastAPI's validation-error handler then fails to JSON-serialize
    (the same hazard ``TenantConfigUpdate.theme_color`` avoids by using a
    native ``pattern``). Cross-field ordering can't be a native constraint,
    so the check lives in the service (``BookingService.create`` /
    ``update``) as a ``BizError`` → 400, which serializes cleanly.
    """


class BookingUpdate(BaseModel):
    """PUT /bookings/{id} body.

    Per D10, only ``pending`` bookings may be updated, and only
    ``scheduled_*`` / ``customer_id`` / ``notes`` are mutable.
    ``device_id`` is intentionally absent: changing the device is a
    cancel-and-recreate (prevents "revive a cancelled booking by moving it"),
    and re-pointing device_id would also need its own overlap re-check on a
    different device's slot set.

    Like ``BookingCreate``, this carries NO ``status`` / ``started_at`` /
    ``ended_at`` / ``feedback``. The end>start invariant is enforced in the
    service (see ``BookingCreate`` docstring) because it depends on the
    stored values when only one side is patched.
    """

    customer_id: str | None = Field(default=None, max_length=32)
    scheduled_start_at: datetime | None = None
    scheduled_end_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)


class BookingRead(BaseModel):
    """Within-store read shape (slice 01). ``tenant_id`` is the caller's own
    tenant — exposing it is harmless and keeps the DTO self-describing for the
    frontend (mirrors ``DeviceRead``)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    device_id: str | None = None
    customer_id: str | None = None
    created_by: str | None = None
    status: BookingStatus
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    feedback: dict | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class BookingHqRead(BookingRead):
    """HQ panorama read shape — cross-tenant viewer (super_admin / hq_staff).

    Extends ``BookingRead`` with three display fields that name the related
    rows (tenant / device / customer) so the HQ UI can render a single booking
    row without N client-side lookups. ``tenant_id`` / ``device_id`` /
    ``customer_id`` are inherited from the base (the panorama needs
    ``tenant_id`` to *group* bookings by store, and ``device_id`` /
    ``customer_id`` to disambiguate when two stores reuse the same name).

    ``*_name`` are nullable because the related row may be gone: a soft-deleted
    tenant, a device whose ``device_id`` is NULL (walk-in / orphaned — the FK
    is SET NULL on hard-delete; under the current soft-delete-only device path
    a soft-deleted device still has a row, so ``device_name`` surfaces), or a
    walk-in booking with no customer binding. The HQ view still renders the
    booking — a missing name shows as None rather than hiding the row (an HQ
    viewer needs the full ledger, including walk-ins and orphaned device
    references).

    Note: ``device_name`` is sourced from ``Device.serial_number`` (devices have
    no ``name`` column — ``serial_number`` IS their business identifier; see
    ``BookingService._to_hq_read``). The field is named ``device_name`` for
    frontend symmetry with ``tenant_name`` / ``customer_name``.
    """

    tenant_name: str | None = None
    device_name: str | None = None
    customer_name: str | None = None


# Re-export for callers that need it.
__all__ = [
    "BookingCreate",
    "BookingHqRead",
    "BookingRead",
    "BookingStatus",
    "BookingUpdate",
]
