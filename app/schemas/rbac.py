"""Pydantic schemas for roles and permissions."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    code: str
    description: str | None = None
    is_system: bool = False
    sort_order: int = 0
    status: str = "active"
    created_at: datetime | None = None


class RoleLabel(BaseModel):
    """Lightweight role option for dropdowns."""

    id: str
    name: str
    code: str


class RoleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    code: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    sort_order: int = 0


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=255)
    sort_order: int | None = None
    status: str | None = None
