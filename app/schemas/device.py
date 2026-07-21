"""Pydantic schemas for device DTOs.

Slice 01 covers the within-store CRUD shape only. The HQ panorama DTO
(``DeviceHqRead`` with tenant_name / model_name / customer_name) and the
bind/unbind DTOs are added in later slices (03 / 04) when they're actually
exercised — kept out of slice 01 so the surface stays minimal.

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
