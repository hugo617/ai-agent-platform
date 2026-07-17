"""Shared FastAPI dependencies: DB session, current user, tenant, permission guard.

These compose into a clean Controller layer: each route declares its needs
through ``Depends`` and the heavy lifting (auth, tenancy, authorization) is
centralised here.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import (
    TokenError,
    decode_token,
    extract_platform_role,
    extract_subject,
    extract_tenant,
)
from app.repositories.tenant import UserRepository, UserTenantRepository
from app.services.permission_service import is_cross_tenant_viewer, permission_service

# AtoA API tokens use this prefix so get_current_user can route them to the
# token bypass without touching the JWT path. ``ahp_`` = agenthub platform.
API_TOKEN_PREFIX = "ahp_"
# How many chars after the prefix form the indexed lookup key. Long enough that
# the prefix is effectively unique per token (narrows auth to ~1 row), short
# enough to stay human-readable in the masked display.
API_TOKEN_PREFIX_LEN = 12

# Standard "Authorization: Bearer <token>" security scheme.
#
# Using HTTPBearer (instead of a raw ``Header`` parameter) makes FastAPI expose
# a proper securityScheme in the OpenAPI spec. API clients (Apifox, Swagger UI,
# generated SDKs) then auto-fill the token from a single "Auth" field instead of
# shipping an empty ``authorization`` header that conflicts with a manual one.
#
# ``auto_error=False``: HTTPBearer's default raises HTTP 403 on a missing/
# malformed header, but the HTTP-correct status for "no credentials" is 401
# (Unauthorized), not 403 (Forbidden). We therefore disable its built-in error
# and raise 401 ourselves in get_current_user, preserving the original contract.
bearer_scheme = HTTPBearer(auto_error=False)


class CurrentUser:
    """Resolved request principal — passed to services as a small value object."""

    def __init__(
        self,
        user_id: str,
        tenant_id: str,
        email: str | None = None,
        jti: str | None = None,
        platform_role: str | None = None,
    ) -> None:
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.email = email
        # Token id (jti). None for tokens without one (e.g. mocked in tests).
        self.jti = jti
        # Platform-level role ("super_admin" or None for normal users).
        self.platform_role = platform_role


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
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
    # bearer_scheme uses auto_error=False, so a missing/malformed header arrives
    # here as None. Raise the HTTP-correct 401 (not HTTPBearer's default 403).
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials

    # AtoA bypass: long-lived API tokens carry an ``ahp_`` prefix. They never
    # reach the JWT path — resolving one constructs a CurrentUser bound to the
    # token's issuer + tenant, so every existing route + permission guard works
    # unchanged. Anything without the prefix falls through to the JWT path
    # (zero regression for the three existing token kinds).
    if token.startswith(API_TOKEN_PREFIX):
        return await _resolve_api_token(token, db)

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
    platform_role = extract_platform_role(claims) or (
        getattr(user, "platform_role", None) if user else None
    )
    return CurrentUser(
        user_id=user_id, tenant_id=tenant_id, email=email, jti=jti_str, platform_role=platform_role
    )


async def _resolve_api_token(token: str, db: AsyncSession) -> CurrentUser:
    """Resolve an ``ahp_`` API token to its issuer's CurrentUser.

    This is the AtoA auth path: the presented token is looked up by prefix
    (indexed), each candidate is decrypted and compared, and on a hit we build a
    CurrentUser bound to the token's ``created_by_user_id`` + fixed
    ``tenant_id``. From there ``require_permission`` / tenant-scoped repos work
    unchanged — the token inherits the issuer's casbin role and cannot escape
    its tenant.

    Re-validates the issuer account (exists, active, still a member) so a token
    is voided the moment its user is disabled or removed from the tenant, even
    though the token itself has no expiry. ``last_used_at`` is refreshed.

    Populates ``current_token_ctx`` with the token's scope context so that
    ``permission_service.check`` (and the LangGraph tool-internal checks, which
    run in the StreamingResponse's child task) can enforce the restricted-scope
    gate. See ``app/api/token_context.py`` for why this is a contextvar.
    """
    # Lazy import avoids a circular dependency at module load time: the service
    # imports repos which import models, and deps is imported very early.
    from app.api.token_context import TokenCtx, current_token_ctx
    from app.services.api_token_service import api_token_service

    resolved = await api_token_service.verify(db, token)
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired API token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = resolved.user_id
    tenant_id = resolved.tenant_id

    # Re-validate membership + account state, mirroring the JWT path, so token
    # revocation takes effect through the user account too.
    membership = await UserTenantRepository(db).get_membership(user_id, tenant_id)
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token issuer is no longer a member of this tenant",
        )
    user = await UserRepository(db).get(user_id)
    if user is None or user.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="token issuer account no longer exists"
        )
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"token issuer account is {user.status}; access denied",
        )

    # Populate the request-scoped token context. Set BEFORE returning so the
    # downstream ``require_permission`` dependency, the endpoint body, and the
    # StreamingResponse generator (run in a child task that inherits this
    # contextvar via asyncio's copy_context) all observe it.
    ctx = TokenCtx(
        token_id=resolved.token_id,
        scopes=list(resolved.scopes),
        scope_mode=resolved.scope_mode,
    )
    current_token_ctx.set(ctx)

    return CurrentUser(
        user_id=user_id,
        tenant_id=tenant_id,
        email=user.email,
        platform_role=getattr(user, "platform_role", None),
    )


def require_permission(obj: str, act: str):
    """Build a dependency that enforces ``(obj, act)`` for the current tenant.

    Usage in a router::

        @router.post("/", dependencies=[Depends(require_permission("agents", "create"))])
    """

    async def _guard(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        allowed = await permission_service.check(
            user.user_id, user.tenant_id, obj, act, platform_role=user.platform_role
        )
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"无权限：不能执行 {act} 操作于 {obj}",
            )
        return user

    return _guard


def require_super_admin():
    """Build a dependency that only platform super admins satisfy.

    Used by platform-wide endpoints (e.g. the platform-level LLM config, Group
    writes) where no tenant-scoped permission exists — the action crosses all
    tenants, so a tenant role like owner/admin must NOT be enough on its own.
    """

    async def _guard(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.platform_role != "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权限：需要平台超级管理员",
            )
        return user

    return _guard


def require_cross_tenant_viewer():
    """Build a dependency satisfied by any cross-tenant viewer.

    ``super_admin`` (full power) and ``hq_staff`` (read-only HQ viewer) both
    pass. Used by cross-tenant *read* endpoints (e.g. the Customer HQ
    aggregation) where hq_staff needs the panorama but must NOT be able to
    reach the write endpoints (those stay behind ``require_super_admin``).
    """

    async def _guard(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not is_cross_tenant_viewer(user.platform_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权限：需要总部角色(super_admin 或 hq_staff)",
            )
        return user

    return _guard
