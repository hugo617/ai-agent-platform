"""Pydantic schemas for tenant DTOs.

User DTOs live in ``app/schemas/user.py``; this module only holds Tenant
create/read shapes.
"""

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
