"""Pydantic schemas for device DTOs.

Two read shapes: ``DeviceRead`` (within-store CRUD, slice 01) and
``DeviceHqRead`` (HQ panorama, slice 03). ``DeviceHqRead`` extends
``DeviceRead`` with four cross-tenant display fields (``tenant_name``,
``model_name``, ``customer_name``, and ``tenant_id`` already on the base) so a
super_admin / hq_staff viewer can see *which store* a device belongs to without
a second lookup. Bind/unbind DTOs land in slice 04.

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
