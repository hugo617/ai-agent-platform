"""SQLAlchemy engine + session factory.

All repositories receive an ``AsyncSession`` via FastAPI dependency injection,
keeping data access code fully async and testable.

The engine and session factory are created lazily (on first attribute access,
via the module-level ``__getattr__`` below) rather than at import time. This
matters because Alembic's ``env.py`` imports ``Base`` from this module to drive
``--autogenerate`` / migration application, and the migration DSN is a *sync*
URL (e.g. ``sqlite:///...`` or ``postgresql+psycopg://...``). Building an async
engine at import time with a sync URL raises immediately ("asyncio extension
requires an async driver"), so the engine is deferred until the app actually
needs it (request handling, ``init_admin``, …), by which point the URL is the
async runtime URL.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """Declarative base shared by all ORM models."""


# NOTE: casbin-sqlalchemy-adapter is sync; we run it through run_in_threadpool
# at the service layer. The app's own data layer stays fully async.

# --- lazy singletons (see module docstring) ---------------------------------
_engine: AsyncEngine | None = None
_AsyncSessionLocal: async_sessionmaker[AsyncSession] | None = None


def _get_engine() -> AsyncEngine:
    """Build the async engine on first use and cache it."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            pool_pre_ping=True,
        )
    return _engine


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Build the session factory on first use and cache it."""
    global _AsyncSessionLocal
    if _AsyncSessionLocal is None:
        _AsyncSessionLocal = async_sessionmaker(
            _get_engine(), class_=AsyncSession, expire_on_commit=False
        )
    return _AsyncSessionLocal


def __getattr__(name: str):
    """Expose ``engine`` / ``AsyncSessionLocal`` lazily (PEP 562).

    Keeps ``from app.core.database import AsyncSessionLocal`` working for
    existing callers (main.py, scripts/init_admin.py) without constructing the
    engine at import time.
    """
    if name == "engine":
        return _get_engine()
    if name == "AsyncSessionLocal":
        return _get_session_factory()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a scoped async session per request."""
    # _get_session_factory() returns the async_sessionmaker (factory); the
    # extra () instantiates an AsyncSession, which is the async context manager.
    async with _get_session_factory()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
