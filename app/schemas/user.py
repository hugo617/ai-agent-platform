"""Pydantic schemas for the user CRUD endpoints.

A user has a profile (username/email/phone/…) and, within each tenant, a role
(stored on ``user_tenants`` and mirrored in casbin). The list endpoint returns
paginated results with summary statistics.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

VALID_STATUSES = {"active", "inactive", "locked"}


class OrganizationBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    code: str | None = None


class RoleBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    code: str


class UserRead(BaseModel):
    """A user as returned by the API (list item or detail)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str | None = None
    email: str | None = None
    display_name: str | None = None
    real_name: str | None = None
    phone: str | None = None
    avatar: str | None = None
    status: str = "active"
    role: RoleBrief | None = None
    organizations: list[OrganizationBrief] = []
    last_login_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # Cross-tenant fields: set only when the caller is a super admin.
    tenant_id: str | None = None
    tenant_name: str | None = None


class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=255)
    display_name: str | None = Field(default=None, max_length=128)
    real_name: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    avatar: str | None = Field(default=None, max_length=255)
    role: str = Field(default="member", max_length=64)
    organization_ids: list[str] = Field(default_factory=list)
    status: str = "active"


class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=2, max_length=50)
    email: EmailStr | None = None
    display_name: str | None = Field(default=None, max_length=128)
    real_name: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    avatar: str | None = Field(default=None, max_length=255)
    role: str | None = Field(default=None, max_length=64)
    organization_ids: list[str] | None = None
    status: str | None = None


class PasswordReset(BaseModel):
    new_password: str = Field(..., min_length=6, max_length=255)


class UserStatusUpdate(BaseModel):
    status: str = Field(..., max_length=20)


class UserListResponse(BaseModel):
    items: list[UserRead]
    total: int
    page: int
    limit: int
    total_pages: int


class UserStatistics(BaseModel):
    total: int
    active: int
    inactive: int
    locked: int
    recent_logins: int  # logged in within the last 30 days
    new_this_month: int


# ---- legacy member DTOs (kept for the /tenants/me/members endpoints) ----

class MemberCreate(BaseModel):
    """Add an existing user (by id) to the current tenant with a role."""

    user_id: str = Field(..., min_length=1, max_length=128)
    role: str = Field("member", min_length=1, max_length=64)
    email: str | None = None
    display_name: str | None = None


class MemberUpdate(BaseModel):
    """Change a member's role within the current tenant."""

    role: str = Field(..., min_length=1, max_length=64)


class MemberRead(BaseModel):
    """A tenant member as seen by the API."""

    model_config = ConfigDict(from_attributes=True)

    user_id: str
    role: str
    email: str | None = None
    display_name: str | None = None
    joined_at: datetime | None = None
