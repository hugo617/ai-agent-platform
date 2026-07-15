"""Pydantic schemas for authentication."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MeResponse(BaseModel):
    user_id: str
    tenant_id: str | None
    email: str | None = None
    platform_role: str | None = None
    roles: list[str] = []
    # All currently-effective permission codes (both "api" units like
    # "customers:read" and "menu" UX codes like "menu:agents"), aggregated from
    # the user's roles via casbin's implicit-permissions walk. Drives the
    # frontend's nav visibility + button-level guards so they no longer hardcode
    # role sets. super_admin gets an empty list here and the frontend bypasses
    # (platform_role === "super_admin" short-circuits every check).
    permissions: list[str] = []
    # Self-service profile fields (priority 49): exposed so the profile page can
    # pre-fill display_name/real_name/phone/avatar rather than starting blank.
    # CurrentUser (from the token) carries none of these, so _build_me_response
    # loads the DB row to populate them.
    display_name: str | None = None
    real_name: str | None = None
    phone: str | None = None
    avatar: str | None = None


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


class ProfileUpdate(BaseModel):
    """Editable fields for the current user's self-service profile.

    Only profile columns the user may change are exposed — ``platform_role`` /
    ``status`` / ``username`` are intentionally absent so a caller cannot
    escalate privileges via the self-service endpoint (``PUT /auth/me`` ignores
    any such fields defensively). Matches the editable subset of ``UserUpdate``
    (app/schemas/user.py).
    """

    model_config = ConfigDict(extra="ignore")

    display_name: str | None = Field(default=None, max_length=128)
    real_name: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    avatar: str | None = Field(default=None, max_length=255)


class PasswordChange(BaseModel):
    """Self-service password change payload (``PUT /auth/me/password``).

    ``old_password`` is verified against the stored bcrypt hash; the caller must
    know the current password (unlike the admin reset, which needs no proof).
    """

    model_config = ConfigDict(extra="ignore")

    old_password: str = Field(..., min_length=1, max_length=255)
    new_password: str = Field(..., min_length=8, max_length=255)
