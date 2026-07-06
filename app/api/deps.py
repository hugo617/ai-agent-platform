"""Shared FastAPI dependencies: DB session, current user, tenant, permission guard.

These compose into a clean Controller layer: each route declares its needs
through ``Depends`` and the heavy lifting (auth, tenancy, authorization) is
centralised here.
"""

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import TokenError, decode_token, extract_subject, extract_tenant
from app.repositories.tenant import UserTenantRepository
from app.services.permission_service import permission_service


class CurrentUser:
    """Resolved request principal — passed to services as a small value object."""

    def __init__(self, user_id: str, tenant_id: str, email: str | None = None) -> None:
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.email = email


def _get_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or malformed Authorization header",
        )
    return authorization.split(" ", 1)[1].strip()


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """Verify the Logto JWT and resolve the active tenant.

    The tenant comes either from a custom JWT claim (``tenant_id``) or, if
    absent, from the user's first membership row. If neither is available the
    request is rejected as 403 — every authenticated request must be scoped to
    exactly one tenant.
    """
    token = _get_bearer(authorization)
    try:
        claims = await decode_token(token)
    except TokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)
        ) from e

    user_id = extract_subject(claims)
    tenant_id = extract_tenant(claims)

    if tenant_id is None:
        memberships = UserTenantRepository(db)
        user_memberships = await memberships.list_for_user(user_id)
        if user_memberships:
            tenant_id = user_memberships[0].tenant_id

    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="user is not associated with any tenant",
        )

    email = claims.get("email")
    return CurrentUser(user_id=user_id, tenant_id=tenant_id, email=email)


def require_permission(obj: str, act: str):
    """Build a dependency that enforces ``(obj, act)`` for the current tenant.

    Usage in a router::

        @router.post("/", dependencies=[Depends(require_permission("agents", "create"))])
    """

    async def _guard(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        allowed = await permission_service.check(user.user_id, user.tenant_id, obj, act)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"forbidden: cannot {act} {obj}",
            )
        return user

    return _guard


def decode_unverified_token_claims(token: str) -> dict:
    """Inspect token claims without verifying (used only for diagnostics)."""
    try:
        return jwt.decode(token, options={"verify_signature": False})
    except jwt.InvalidTokenError:
        return {}
