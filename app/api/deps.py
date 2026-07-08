"""Shared FastAPI dependencies: DB session, current user, tenant, permission guard.

These compose into a clean Controller layer: each route declares its needs
through ``Depends`` and the heavy lifting (auth, tenancy, authorization) is
centralised here.
"""

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import TokenError, decode_token, extract_subject, extract_tenant
from app.repositories.tenant import UserRepository, UserTenantRepository
from app.services.permission_service import permission_service


class CurrentUser:
    """Resolved request principal — passed to services as a small value object."""

    def __init__(
        self,
        user_id: str,
        tenant_id: str,
        email: str | None = None,
        jti: str | None = None,
    ) -> None:
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.email = email
        # Token id (jti). None for tokens without one (e.g. mocked in tests).
        self.jti = jti


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
    """Verify the access token and resolve the active tenant.

    The tenant comes either from a custom JWT claim (``tenant_id``) or, if
    absent, from the user's first membership row. If neither is available the
    request is rejected as 403 — every authenticated request must be scoped to
    exactly one tenant.

    Re-validates three things on every request so that security state changes
    (account disabled/locked, removed from a tenant, logged out) take effect
    immediately instead of waiting for the token to expire:
      1. The user still exists and is not soft-deleted, and is ``active``.
      2. The user is still a member of the token's tenant (rejects removed
         members who keep using an old token).
      3. The token's ``jti`` matches an active ``UserSession`` row, if a session
         was ever recorded for it (logout / "log out everywhere" revoke it).
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
    jti = claims.get("jti")
    jti_str = str(jti) if jti else None

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

    # Re-validate membership + account state so revocation is enforced even
    # before the (stateless) JWT expires.
    membership = await UserTenantRepository(db).get_membership(user_id, tenant_id)
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user is no longer a member of this tenant",
        )
    user = await UserRepository(db).get(user_id)
    if user is None or user.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="account no longer exists"
        )
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"account is {user.status}; access denied",
        )

    # If the token carries a jti and a session row exists, require it to be
    # active (logout marks it inactive). Tokens without a jti (dev/mocked) and
    # tokens whose session row has been purged are allowed through.
    if jti_str is not None:
        from app.repositories.security import SessionRepository

        session = await SessionRepository(db).get_by_session_id(jti_str)
        if session is not None and not session.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="session has been revoked",
            )

    email = claims.get("email") or (user.email if user else None)
    return CurrentUser(user_id=user_id, tenant_id=tenant_id, email=email, jti=jti_str)


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
