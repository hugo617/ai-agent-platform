"""Authentication service — local username/password login + session bookkeeping.

Login flow:
  1. Resolve the user by username/email (must exist, be active, have a password).
  2. Verify the bcrypt hash.
  3. Reject inside the temporary failed-attempt lockout window (if open), or
     count a wrong password toward it (5 consecutive failures lock 15 minutes).
  4. Resolve the tenant from the user's first membership (or reject).
  5. Update ``last_login_at``, write a ``UserSession`` row, mint an HS256 JWT.
  6. Record an audit-log entry.

All distinct failure reasons map to the same 401 message ("invalid credentials")
to avoid leaking which accounts exist — except account status, which we surface
explicitly so the user understands *why* they cannot log in.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.local_auth import create_access_token
from app.core.password import hash_password, verify_password
from app.models.security import UserSession
from app.models.tenant import User
from app.repositories.security import SessionRepository
from app.repositories.tenant import UserRepository, UserTenantRepository
from app.services.logging_service import LoggingService

# A real bcrypt hash generated at import time. We run ``verify_password``
# against it whenever the login identifier doesn't resolve to a real user so
# the response takes roughly the same time as a genuine login (bcrypt is
# deliberately slow) — otherwise an attacker could enumerate accounts by timing.
# Generating it here (rather than hard-coding a literal) guarantees the cost
# factor matches ``settings.salt_rounds`` and the hash is always well-formed.
_DUMMY_HASH = hash_password("dummy-account-enumeration-guard")


class AuthError(Exception):
    """Raised on a login/refresh failure; mapped to HTTP 401 by the router."""


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.memberships = UserTenantRepository(db)
        self.sessions = SessionRepository(db)
        self.logs = LoggingService(db)

    async def login(
        self,
        *,
        identifier: str,
        password: str,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[str, str, str, str]:
        """Authenticate and return ``(access_token, user_id, tenant_id, jti)``.

        Raises ``AuthError`` on any failure.
        """
        user = await self.users.get_by_login_identifier(identifier)
        # Always run exactly one bcrypt verify, whether or not the account
        # exists — this keeps response time roughly constant so an attacker
        # cannot tell which identifiers are real by timing. ``verify_password``
        # returns False for a None hash, so the no-password (OIDC-only) case is
        # covered by the same branch.
        stored_hash = user.password if (user is not None and user.password) else _DUMMY_HASH
        password_ok = verify_password(password, stored_hash)

        # Account-state checks come AFTER the (slow) bcrypt verify so a
        # locked/inactive account takes the same time to reject as a valid one.
        if user is None:
            raise AuthError("invalid credentials")
        if user.status == "locked":
            raise AuthError("account is locked; contact an administrator")
        if user.status != "active":
            raise AuthError("account is not active")
        # Temporary lockout (failed-attempt lock) rejects BEFORE the password
        # verdict: a correct password during the window is refused too, and
        # failures inside the window are neither counted nor renew the lock.
        if _temporarily_locked(user.locked_until):
            raise AuthError("account temporarily locked, try again later")
        if not user.password or not password_ok:
            await self._record_lockout_failure(user, ip=ip)
            raise AuthError("invalid credentials")

        # Resolve tenant from the user's memberships (first wins). A user with
        # no tenant cannot log in through the local flow.
        memberships = await self.memberships.list_for_user(user.id)
        if not memberships:
            raise AuthError("user is not associated with any tenant")
        tenant_id = memberships[0].tenant_id

        # Mint the access token first; its jti doubles as the session id so
        # logout can revoke the row by the same handle. Store a SHA-256 of the
        # token so a future "is this token still active?" check is possible
        # without keeping the raw token around.
        await self.users.update_last_login(user.id)
        # A successful login clears the lockout counter and any residual
        # (already-expired) lock — reaching this line proves the password was
        # correct, so prior failures no longer count.
        await self.users.reset_failed_attempts(user.id)
        token, jti = create_access_token(
            user.id, tenant_id, email=user.email, platform_role=getattr(user, "platform_role", None)
        )
        await self._create_session(
            user.id, jti, token=token, ip=ip, user_agent=user_agent
        )

        await self.logs.record(
            action="login",
            module="auth",
            message=f"user {user.username or user.id} logged in",
            user_id=user.id,
            tenant_id=tenant_id,
            level="info",
            ip=ip,
            user_agent=user_agent,
            session_id=jti,
        )
        await self.db.commit()
        return token, user.id, tenant_id, jti

    async def _record_lockout_failure(self, user: User, *, ip: str | None) -> None:
        """Count one failed local login; lock the account at the threshold.

        Runs on the raise path, so every write below commits inside the
        repository call — otherwise the counter/lock would be discarded with
        the rolled-back request. OIDC-only accounts (password is None) are
        skipped: a lock cannot reach their Logto login path, so counting them
        is a pure denial-of-service surface (knowing the username would be
        enough to trigger it).
        """
        if user.password is None:
            return
        attempts = await self.users.record_failed_attempt(user.id)
        if attempts < settings.login_lockout_threshold:
            return
        # Reset BEFORE locking: reset_failed_attempts also clears locked_until,
        # so locking first would immediately undo the lock. The counter restarts
        # from zero so failures after the unlock re-accumulate from scratch.
        await self.users.reset_failed_attempts(user.id)
        until = datetime.now(UTC) + timedelta(minutes=settings.login_lockout_minutes)
        await self.users.set_locked_until(user.id, until)
        await self.logs.record(
            action="login_locked",
            module="auth",
            message=(
                f"user {user.username or user.id} temporarily locked for "
                f"{settings.login_lockout_minutes} minutes after "
                f"{settings.login_lockout_threshold} failed login attempts"
            ),
            user_id=user.id,
            level="warning",
            ip=ip,
        )
        await self.db.commit()

    async def _create_session(
        self,
        user_id: str,
        jti: str,
        *,
        token: str,
        ip: str | None,
        user_agent: str | None,
    ) -> None:
        """Persist a UserSession row keyed by the token's ``jti``."""
        expires_at = datetime.now(UTC) + timedelta(
            hours=settings.session_ttl_hours
        )
        self.db.add(
            UserSession(
                user_id=user_id,
                session_id=jti,
                device_type=_guess_device_type(user_agent),
                device_name=None,
                platform=_guess_platform(user_agent),
                ip_address=ip,
                user_agent=user_agent,
                expires_at=expires_at,
                is_active=True,
            )
        )
        await self.db.flush()

    async def list_sessions(self, user_id: str) -> list[UserSession]:
        return await self.sessions.list_active_for_user(user_id)

    async def terminate_session(self, user_id: str, session_id: str) -> None:
        """Deactivate a session row; idempotent if already inactive."""
        from sqlalchemy import select

        stmt = select(UserSession).where(UserSession.session_id == session_id)
        result = await self.db.execute(stmt)
        s = result.scalar_one_or_none()
        if s is None or s.user_id != user_id:
            raise AuthError("session not found")
        await self.sessions.deactivate(s)
        await self.db.commit()

    async def logout(self, user_id: str, jti: str | None) -> None:
        if not jti:
            return
        from sqlalchemy import select

        stmt = select(UserSession).where(UserSession.session_id == jti)
        result = await self.db.execute(stmt)
        s = result.scalar_one_or_none()
        if s is not None and s.user_id == user_id:
            await self.sessions.deactivate(s)
            await self.db.commit()


def _temporarily_locked(locked_until: datetime | None) -> bool:
    """True while the failed-attempt lockout window is still open.

    SQLite reads ``DateTime(timezone=True)`` columns back tz-naive (the
    dialect drops the offset), so a naive value is interpreted as UTC before
    comparing; on PostgreSQL values come back tz-aware and the normalization
    is a no-op.
    """
    if locked_until is None:
        return False
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=UTC)
    return locked_until > datetime.now(UTC)


def _guess_device_type(user_agent: str | None) -> str | None:
    if not user_agent:
        return None
    ua = user_agent.lower()
    if "mobile" in ua or "android" in ua or "iphone" in ua:
        return "mobile"
    return "web"


def _guess_platform(user_agent: str | None) -> str | None:
    if not user_agent:
        return None
    ua = user_agent.lower()
    if "windows" in ua:
        return "Windows"
    if "mac os" in ua or "macintosh" in ua:
        return "macOS"
    if "linux" in ua:
        return "Linux"
    if "android" in ua:
        return "Android"
    if "iphone" in ua or "ipad" in ua:
        return "iOS"
    return None


__all__ = ["AuthService", "AuthError"]
