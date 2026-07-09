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


# ----- role ↔ permission grants (SCD2, scenario ii) -----


class RolePermissionGrant(BaseModel):
    """Grant a single ``(obj, act)`` permission to a role.

    The permission catalogue row is upserted under ``code == "<obj>:<act>"``;
    the grant then points the role at it via a current-state ``role_permissions``
    row and resyncs casbin.
    """

    obj: str = Field(..., min_length=1, max_length=64)
    act: str = Field(..., min_length=1, max_length=32)


class RolePermissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str  # role_permissions row id
    role_id: str
    permission_id: str
    obj: str
    act: str
    valid_from: datetime
    valid_to: datetime | None = None
