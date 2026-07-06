"""Pydantic schemas for tenant / user DTOs."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TenantBase(BaseModel):
    name: str


class TenantCreate(TenantBase):
    pass


class TenantRead(TenantBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str | None = None
    display_name: str | None = None
    created_at: datetime


class UserTenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    tenant: TenantRead
    role: str
