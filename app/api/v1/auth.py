"""Auth endpoints.

  - ``GET  /auth/me``        — current principal (Logto, dev-token, or local).
  - ``POST /auth/login``     — local username/password → HS256 access token.
  - ``POST /auth/logout``    — revoke the calling session.
  - ``GET  /auth/sessions``  — list the caller's active sessions.
  - ``DELETE /auth/sessions/{session_id}`` — terminate one session.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.security import TokenError, decode_token
from app.repositories.tenant import UserRepository
from app.schemas.auth import (
    LoginRequest,
    MeResponse,
    SessionRead,
    TokenResponse,
)
from app.services.auth_service import AuthError, AuthService
from app.services.permission_service import permission_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=MeResponse)
async def me(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    roles = await permission_service.get_roles_for_user_in_domain(
        user.user_id, user.tenant_id
    )
    # Read platform_role from the user row (authoritative, not the JWT).
    platform_role = user.platform_role
    if platform_role is None:
        db_user = await UserRepository(db).get(user.user_id)
        platform_role = db_user.platform_role if db_user else None

    # Aggregate every currently-effective permission code (api + menu) for the
    # frontend's nav/button guards. super_admin bypasses all checks, so we skip
    # the casbin walk and return [] — the frontend short-circuits on
    # platform_role === "super_admin".
    permissions: list[str] = []
    if platform_role != "super_admin" and user.tenant_id is not None:
        implicit = await permission_service.get_implicit_permissions_for_user(
            user.user_id, user.tenant_id
        )
        # Each row is [sub, dom, obj, act]; collapse to "<obj>:<act>" codes.
        permissions = [f"{row[2]}:{row[3]}" for row in implicit if len(row) >= 4]

    return MeResponse(
        user_id=user.user_id,
        tenant_id=user.tenant_id,
        email=user.email,
        platform_role=platform_role,
        roles=roles,
        permissions=permissions,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate with username/email + password and return an access token.

    Public endpoint — no bearer required. The returned token is then used as a
    bearer for all subsequent requests, identical to a Logto/dev token.
    """
    identifier = (payload.username or payload.email or "").strip()
    if not identifier:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="username or email is required",
        )

    service = AuthService(db)
    try:
        token, user_id, tenant_id, _jti = await service.login(
            identifier=identifier,
            password=payload.password,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except AuthError as e:
        # All auth failures → 401 with the service's message.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)
        ) from e

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.access_token_ttl_minutes * 60,
        user_id=user_id,
        tenant_id=tenant_id,
    )


async def _jti_from_request(request: Request) -> str | None:
    """Extract the ``jti`` claim from the request's bearer token (if any)."""
    authorization = request.headers.get("authorization")
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = await decode_token(token)
    except TokenError:
        return None
    jti = claims.get("jti")
    return str(jti) if jti else None


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Revoke the calling session (best-effort: idempotent if already gone)."""
    jti = await _jti_from_request(request)
    await AuthService(db).logout(user.user_id, jti)


@router.get("/sessions", response_model=list[SessionRead])
async def list_sessions(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SessionRead]:
    rows = await AuthService(db).list_sessions(user.user_id)
    return [SessionRead.model_validate(r) for r in rows]


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def terminate_session(
    session_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await AuthService(db).terminate_session(user.user_id, session_id)
    except AuthError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        ) from e
