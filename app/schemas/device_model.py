"""Pydantic schemas for device_model DTOs.

Two read shapes: ``DeviceModelRead`` (full fields incl. ``unit_cost`` +
complete ``specs``) for super_admin / hq_staff, and
``DeviceModelPublicRead`` (only ``id``, ``name``, ``specs.form_factor``)
for tenant users — the device-picker dropdown only needs these. The
service picks which to return based on ``platform_role``.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DeviceModelBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    brand: str | None = Field(None, max_length=200)
    supplier: str | None = Field(None, max_length=200)
    # No ``ge=0`` here: Pydantic surfaces the raw Decimal in the 422 error
    # detail, which starlette's JSONResponse can't serialize. The non-negativity
    # invariant is enforced in the service (BizError 400) — matches the project
    # convention for money columns (see model_pricing, which also has no ge).
    unit_cost: Decimal
    # Free-form physical specs. PUT semantics = whole-replace.
    specs: dict[str, Any] = Field(default_factory=dict)


class DeviceModelCreate(DeviceModelBase):
    pass


class DeviceModelUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    brand: str | None = Field(None, max_length=200)
    supplier: str | None = Field(None, max_length=200)
    unit_cost: Decimal | None = None
    specs: dict[str, Any] | None = None


class DeviceModelRead(DeviceModelBase):
    """Full view for super_admin / hq_staff (cross-tenant viewers)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime


class DeviceModelPublicRead(BaseModel):
    """Minimal view for tenant users — just enough for the device-picker
    dropdown. ``unit_cost`` and the rest of ``specs`` are stripped."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    specs: dict[str, Any]
