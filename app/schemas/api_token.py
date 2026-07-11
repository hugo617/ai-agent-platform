"""Pydantic schemas for API token DTOs.

The plaintext token is returned **only** in :class:`ApiTokenCreateResponse` (the
one-time response to issuing a token). Every other response uses
:class:`ApiTokenRead`, which carries just the masked prefix — never the
plaintext, never the ciphertext.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ApiTokenCreate(BaseModel):
    """Payload for POST /api-tokens (issue a new token)."""

    name: str = Field(..., min_length=1, max_length=128)
    expires_at: datetime | None = None
    scopes: list[str] = Field(default_factory=list)


class ApiTokenCreateResponse(BaseModel):
    """One-time response to issuing a token — includes the plaintext token.

    The caller must store the token now; it is never retrievable again.
    """

    model_config = ConfigDict(from_attributes=True)

    token: str
    token_id: str
    name: str
    token_prefix: str
    scopes: list[str]
    expires_at: datetime | None
    created_at: datetime


class ApiTokenRead(BaseModel):
    """Masked token row returned by GET /api-tokens — no plaintext, no ciphertext."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    token_prefix: str
    token_type: str
    scopes: list[str]
    last_used_at: datetime | None
    expires_at: datetime | None
    is_active: bool
    created_at: datetime
