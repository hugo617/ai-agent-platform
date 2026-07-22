"""Pydantic schemas for device DTOs.

Two read shapes: ``DeviceRead`` (within-store CRUD, slice 01) and
``DeviceHqRead`` (HQ panorama, slice 03). ``DeviceHqRead`` extends
``DeviceRead`` with four cross-tenant display fields (``tenant_name``,
``model_name``, ``customer_name``, and ``tenant_id`` already on the base) so a
super_admin / hq_staff viewer can see *which store* a device belongs to without
a second lookup. ``DeviceBindRequest`` / ``DeviceBindResponse`` (slice 04)
model the bind action endpoint.

``DeviceStatus`` is a Literal (not an Enum) so the 422-on-bad-value behaviour
falls out of Pydantic for free and the CHECK constraint in the DB is a
defence-in-depth backstop.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DeviceStatus = Literal["active", "maintenance", "retired"]


class DeviceBase(BaseModel):
    model_id: str = Field(..., min_length=1, max_length=32)
    serial_number: str = Field(..., min_length=1, max_length=200)
    status: DeviceStatus = "active"


class DeviceCreate(DeviceBase):
    # Optional initial customer binding — slice 04 will use the dedicated
    # bind endpoint, but a create-time hint is convenient for tests/seed.
    customer_id: str | None = Field(default=None, max_length=32)


class DeviceUpdate(BaseModel):
    model_id: str | None = Field(default=None, min_length=1, max_length=32)
    serial_number: str | None = Field(default=None, min_length=1, max_length=200)
    status: DeviceStatus | None = None
    # customer_id via this endpoint is intentionally NOT supported — bind /
    # unbind have their own dedicated endpoints (slice 04) so the audit trail
    # stays clean.


class DeviceRead(BaseModel):
    """Within-store read shape. ``tenant_id`` is the caller's own tenant —
    exposing it is harmless (you already know your own tenant) and keeps the
    DTO self-describing for the frontend."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    model_id: str
    serial_number: str
    status: DeviceStatus
    customer_id: str | None = None
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime


class DeviceHqRead(DeviceRead):
    """HQ panorama read shape — cross-tenant viewer (super_admin / hq_staff).

    Extends ``DeviceRead`` with three display fields that name the related
    rows (tenant / model / customer) so the HQ UI can render a single device
    row without N client-side lookups. ``tenant_id`` is inherited from the
    base (the panorama needs it to *group* devices by store).

    ``*_name`` are nullable because the related row may be soft-deleted or,
    for ``customer_name``, the device may have no binding at all
    (``customer_id`` is optional). The HQ view still renders the device —
    a deleted tenant/model/customer name simply shows as None rather than
    hiding the device (an HQ viewer needs to see the full inventory).
    """

    tenant_name: str | None = None
    model_name: str | None = None
    customer_name: str | None = None


# --------------------------------------------------------------- bind (slice 04)
#
# Bind is modelled as a POST-to-a-sub-resource action (``POST /devices/{id}/bind``)
# rather than a resource create, so it returns **200, not 201** — the device
# already exists; bind just assigns its ``customer_id``. ``already_bound`` lets
# the caller distinguish "newly bound" (``False``) from "idempotent repeat of
# the same customer" (``True``, no write happened) without a second GET.


class DeviceBindRequest(BaseModel):
    """Body of ``POST /devices/{id}/bind``.

    ``customer_id`` is the *global* Customer id (``customers.id``). The bind
    succeeds only if that customer has a *live* ``CustomerProfile`` in the
    caller's tenant — enforced in the service via ``CustomerProfileRepository.
    get_by_customer_tenant``. A nonexistent customer and a customer that
    exists only in another tenant both collapse to the same 400 (no
    enumeration leak, mirroring the device cross-tenant → 404 defence).
    """

    customer_id: str = Field(..., min_length=1, max_length=32)


class DeviceBindResponse(BaseModel):
    """Body of the 200 returned by ``POST /devices/{id}/bind``.

    ``already_bound`` is the idempotency flag: ``True`` means the device was
    already bound to this exact customer, so the request was a no-op (no DB
    write); ``False`` means a new binding was written (either a first-time
    bind or an overwrite of a previous customer).
    """

    device_id: str
    customer_id: str
    already_bound: bool
