"""Pydantic schemas for API token DTOs.

The plaintext token is returned **only** in :class:`ApiTokenCreateResponse` (the
one-time response to issuing a token). Every other response uses
:class:`ApiTokenRead`, which carries just the masked prefix — never the
plaintext, never the ciphertext.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# The two scope-gate modes (api-token-fine-grained-scopes):
#   "full"       — token inherits the grantor's CURRENT permissions at check
#                  time (check skips the scope gate). Behaviour-equivalent to
#                  pre-scope legacy tokens; the backfill target.
#   "restricted" — only ``scopes`` (intersected live with the grantor's current
#                  permissions) are allowed. Default for new tokens.
ScopeMode = Literal["full", "restricted"]


class ApiTokenCreate(BaseModel):
    """Payload for POST /api-tokens (issue a new token)."""

    name: str = Field(..., min_length=1, max_length=128)
    expires_at: datetime | None = None
    scopes: list[str] = Field(default_factory=list)
    # Default "restricted" so new tokens are least-privilege by default; the
    # issuer must opt into "full" explicitly. The service layer intersects
    # ``scopes`` with the grantor's current permissions at issue time and
    # raises ScopeError (422) if the intersection is empty — schema-level
    # validation can't do this because it can't see the grantor's perms.
    scope_mode: ScopeMode = "restricted"


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
    scope_mode: ScopeMode
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
    scope_mode: ScopeMode
    last_used_at: datetime | None
    expires_at: datetime | None
    is_active: bool
    created_at: datetime
