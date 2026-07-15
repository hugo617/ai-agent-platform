"""Auth endpoints.

  - ``GET  /auth/me``        — current principal (Logto, dev-token, or local).
  - ``PUT  /auth/me``        — self-service profile edit (current user only).
  - ``PUT  /auth/me/password``— self-service password change (verify old → new).
  - ``POST /auth/login``     — local username/password → HS256 access token.
  - ``POST /auth/logout``    — revoke the calling session.
  - ``GET  /auth/sessions``  — list the caller's active sessions.
  - ``DELETE /auth/sessions/{session_id}`` — terminate one session.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.password import hash_password, verify_password
from app.core.security import TokenError, decode_token
from app.repositories.tenant import UserRepository
from app.schemas.auth import (
    LoginRequest,
    MeResponse,
    PasswordChange,
    ProfileUpdate,
    SessionRead,
    TokenResponse,
)
from app.services.auth_service import AuthError, AuthService
from app.services.permission_service import permission_service

router = APIRouter(prefix="/auth", tags=["auth"])


async def _build_me_response(user: CurrentUser, db: AsyncSession) -> MeResponse:
    """Assemble MeResponse for the current principal (shared by GET + PUT /me)."""
    roles = await permission_service.get_roles_for_user_in_domain(
        user.user_id, user.tenant_id
    )
    # The token's CurrentUser carries only id/tenant/email/platform_role, so the
    # profile columns (display_name/real_name/phone/avatar) and the authoritative
    # platform_role must be read from the DB. Load once and reuse for both.
    db_user = await UserRepository(db).get(user.user_id)
    platform_role = user.platform_role
    if platform_role is None and db_user is not None:
        platform_role = db_user.platform_role

    permissions: list[str] = []
    if platform_role != "super_admin" and user.tenant_id is not None:
        implicit = await permission_service.get_implicit_permissions_for_user(
            user.user_id, user.tenant_id
        )
        permissions = [f"{row[2]}:{row[3]}" for row in implicit if len(row) >= 4]

    return MeResponse(
        user_id=user.user_id,
        tenant_id=user.tenant_id,
        email=user.email,
        platform_role=platform_role,
        roles=roles,
        permissions=permissions,
        display_name=db_user.display_name if db_user else None,
        real_name=db_user.real_name if db_user else None,
        phone=db_user.phone if db_user else None,
        avatar=db_user.avatar if db_user else None,
    )


@router.get("/me", response_model=MeResponse)
async def me(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    return await _build_me_response(user, db)


@router.put("/me", response_model=MeResponse)
async def update_me(
    payload: ProfileUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    """Self-service profile edit.

    Only the editable profile columns (display_name/real_name/phone/avatar) are
    applied; platform_role/status/username are NOT exposed on the schema and any
    such fields in the body are dropped (``extra="ignore"``). The target user is
    ALWAYS the token's ``user_id`` — there is no user_id in the body to honor,
    so privilege escalation is impossible.
    """
    repo = UserRepository(db)
    db_user = await repo.get(user.user_id)
    if db_user is None or db_user.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账户不存在")

    changed = False
    for field in ("display_name", "real_name", "phone", "avatar"):
        value = getattr(payload, field)
        if value is not None and value != getattr(db_user, field):
            setattr(db_user, field, value)
            changed = True
    if changed:
        db_user.updated_by = user.user_id
        await db.commit()

    return await _build_me_response(user, db)


@router.put("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: PasswordChange,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Self-service password change.

    Verifies ``old_password`` against the stored bcrypt hash before applying the
    new one. A wrong old password → 400. OIDC-only accounts (no password set)
    cannot change their password here → 400. The new password is hashed with the
    same bcrypt helper used at login (``hash_password``); password_updated_at is
    refreshed to match the admin reset path.
    """
    repo = UserRepository(db)
    db_user = await repo.get(user.user_id)
    if db_user is None or db_user.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账户不存在")
    if not db_user.password:
        # OIDC-only account (Logto manages auth). Surface a clear reason.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该账户未设置本地密码,无法自助修改",
        )
    if not verify_password(payload.old_password, db_user.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="旧密码不正确"
        )

    db_user.password = hash_password(payload.new_password)
    db_user.password_updated_at = datetime.now(UTC)
    db_user.updated_by = user.user_id
    await db.commit()


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
