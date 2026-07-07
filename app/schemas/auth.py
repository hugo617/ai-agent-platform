"""Pydantic schemas for authentication."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MeResponse(BaseModel):
    user_id: str
    tenant_id: str | None
    email: str | None = None
    roles: list[str] = []


class LoginRequest(BaseModel):
    """Username/password login payload.

    Either ``username`` or ``email`` identifies the account; ``password`` is
    verified against the stored bcrypt hash. At least one identifier is required.
    """

    username: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=255)
    password: str = Field(..., min_length=1, max_length=255)

    model_config = ConfigDict(extra="ignore")


class TokenResponse(BaseModel):
    """Access token returned by ``POST /auth/login`` (and dev/token)."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    tenant_id: str


class SessionRead(BaseModel):
    """A login session, as shown in the 'active sessions' view."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    device_type: str | None = None
    device_name: str | None = None
    platform: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    is_active: bool
    expires_at: datetime
    created_at: datetime
    last_accessed_at: datetime
