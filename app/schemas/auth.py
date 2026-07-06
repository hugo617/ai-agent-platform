"""Auth-related schemas."""

from pydantic import BaseModel


class TokenClaims(BaseModel):
    """A flattened view of the JWT claims we care about."""

    sub: str
    tenant_id: str | None = None
    email: str | None = None


class MeResponse(BaseModel):
    user_id: str
    tenant_id: str | None
    email: str | None = None
    roles: list[str] = []
