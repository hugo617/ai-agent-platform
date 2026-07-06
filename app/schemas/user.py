"""Pydantic schemas for tenant member (user) DTOs.

A "member" here is a (user, role) pair within a tenant — i.e. a row in the
``user_tenants`` association table. CRUD over members is how the tenant owner
manages who can access the tenant and with which role.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MemberCreate(BaseModel):
    """Add an existing user (by id) to the current tenant with a role."""

    user_id: str = Field(..., min_length=1, max_length=128)
    role: str = Field("member", min_length=1, max_length=64)
    # Optional profile fields, applied if the user row is created on the fly.
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
    # When the user was linked to this tenant.
    joined_at: datetime | None = None
