"""Pydantic schemas for tenant DTOs.

User DTOs live in ``app/schemas/user.py``; this module only holds Tenant
create/read/update shapes.

``member_count`` on ``TenantRead`` is a *runtime aggregate* (COUNT of active
``user_tenants`` rows), not a persisted column — it is populated by the service
layer when building the read model for the platform-level list/detail views.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TenantBase(BaseModel):
    name: str


class TenantCreate(TenantBase):
    pass


class TenantRead(TenantBase):
    """Tenant read view.

    ``member_count`` defaults to 0 and is only meaningful for responses built
    by the platform-level list/detail endpoints (``GET /tenants/all``,
    ``GET /tenants/{id}``). The user-scoped ``GET /tenants/`` (my tenants) does
    not aggregate and leaves it at 0.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str = "active"
    description: str | None = None
    address: str | None = None
    created_by: str | None = None
    member_count: int = 0
    created_at: datetime


class TenantUpdate(BaseModel):
    """Partial update payload for ``PUT /tenants/{id}`` (super_admin only)."""

    name: str | None = None
    status: str | None = None
    description: str | None = None
    address: str | None = None
