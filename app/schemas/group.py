"""Pydantic schemas for group DTOs."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TenantBrief(BaseModel):
    """Minimal tenant info for embedding in a GroupRead (frontend rendering)."""

    id: str
    name: str | None = None


class GroupBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    code: str | None = Field(None, max_length=100)
    address: str | None = Field(None, max_length=500)
    description: str | None = None
    status: str = "active"
    sort_order: int = 0


class GroupCreate(GroupBase):
    # Tenants to attach at creation time (optional; can attach later).
    tenant_ids: list[str] = Field(default_factory=list)


class GroupUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    code: str | None = Field(None, max_length=100)
    address: str | None = Field(None, max_length=500)
    description: str | None = None
    status: str | None = None
    sort_order: int | None = None


class GroupRead(GroupBase):
    """A group with its attached tenants expanded for the frontend.

    ``tenant_ids`` and ``tenants`` are populated by the service layer (not ORM
    columns) — the service joins through ``GroupTenant`` to fill them.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_ids: list[str] = Field(default_factory=list)
    tenants: list[TenantBrief] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
