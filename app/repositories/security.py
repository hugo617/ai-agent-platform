"""Repositories for sessions and login methods."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.security import UserLoginMethod, UserSession
from app.repositories.base import BaseRepository


class SessionRepository(BaseRepository[UserSession]):
    model = UserSession

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def list_active_for_user(self, user_id: str) -> list[UserSession]:
        stmt = (
            select(UserSession)
            .where(
                UserSession.user_id == user_id,
                UserSession.is_active.is_(True),
                UserSession.expires_at > datetime.utcnow(),
            )
            .order_by(UserSession.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def deactivate(self, session: UserSession) -> None:
        session.is_active = False
        await self.db.flush()

    async def deactivate_all_for_user(
        self, user_id: str, except_session_id: str | None = None
    ) -> int:
        """Bulk-revoke a user's sessions (for a future "log out everywhere").

        Currently unused — wired when the corresponding endpoint lands.
        """
        rows = await self.list_active_for_user(user_id)
        count = 0
        for s in rows:
            if except_session_id and s.session_id == except_session_id:
                continue
            s.is_active = False
            count += 1
        if count:
            await self.db.flush()
        return count


class LoginMethodRepository(BaseRepository[UserLoginMethod]):
    model = UserLoginMethod

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    def add_local_email(self, user_id: str, email: str, *, primary: bool = True) -> UserLoginMethod:
        """Stage a primary email login-method row (caller flushes/commits)."""
        m = UserLoginMethod(
            user_id=user_id,
            login_type="email",
            identifier=email,
            is_verified=False,
            is_primary=primary,
        )
        self.db.add(m)
        return m
