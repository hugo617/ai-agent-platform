"""Shared pytest fixtures.

Hermetic test setup (no external Postgres / Logto required):
  - One in-memory SQLite connection (StaticPool) per test, shared by the
    assertion ``db_session`` and the FastAPI request sessions.
  - JWT verification mocked so we can impersonate any user/tenant.
  - pycasbin uses a file-backed enforcer seeded per test.
"""

import os
import tempfile
import uuid
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

# Configure test environment BEFORE importing the app — must run first.
os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


def _make_casbin(owner_user: str, tenant_id: str):
    """Build a fresh file-backed enforcer and seed default policies."""
    import casbin
    from casbin.persist.adapters import FileAdapter

    policy_file = os.path.join(tempfile.mkdtemp(), "policy.csv")
    open(policy_file, "w").close()
    e = casbin.Enforcer("casbin_model.conf", FileAdapter(policy_file))
    e.add_role_for_user_in_domain(owner_user, "owner", tenant_id)
    for obj, act in [
        ("agents", "read"), ("agents", "create"), ("agents", "update"),
        ("agents", "delete"), ("conversations", "read"),
        ("conversations", "create"), ("conversations", "chat"),
        ("users", "read"), ("users", "create"), ("users", "update"), ("users", "delete"),
    ]:
        e.add_policy("owner", tenant_id, obj, act)
    for obj, act in [
        ("agents", "read"), ("conversations", "read"),
        ("conversations", "create"), ("conversations", "chat"),
    ]:
        e.add_policy("member", tenant_id, obj, act)
    return e


class _TestEnv:
    """Bundles the engine + a session factory + the seeded identity."""

    def __init__(self, engine, factory, owner_user, tenant_id, enforcer) -> None:
        self.engine = engine
        self.factory = factory
        self.owner_user = owner_user
        self.tenant_id = tenant_id
        self.enforcer = enforcer


@pytest_asyncio.fixture
async def test_env() -> AsyncIterator[_TestEnv]:
    """Build the full per-test environment: engine, schema, identity, enforcer."""
    from app.core.database import Base

    # Ensure models are imported so they register on metadata.
    from app.models import agent, message, tenant  # noqa: F401

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    owner_user = f"user-{uuid.uuid4().hex}"
    tenant_id = f"tnt-{uuid.uuid4().hex}"
    enforcer = _make_casbin(owner_user, tenant_id)

    yield _TestEnv(engine, factory, owner_user, tenant_id, enforcer)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_env: _TestEnv) -> AsyncIterator[AsyncSession]:
    """Direct DB session for assertions (shares the test's single connection)."""
    async with test_env.factory() as session:
        yield session


@pytest_asyncio.fixture
async def tenant_owner(test_env: _TestEnv) -> dict:
    return {"user_id": test_env.owner_user, "tenant_id": test_env.tenant_id}


@pytest_asyncio.fixture
async def app_client(test_env: _TestEnv) -> AsyncIterator[AsyncClient]:
    """FastAPI test client wired to the test engine, seeded casbin, mock JWT."""
    from contextlib import asynccontextmanager

    from app.api import deps as deps_mod
    from app.core import casbin_enforcer as casbin_mod
    from app.core.database import get_db
    from app.main import create_app

    app = create_app()

    # Disable lifespan: it would call get_enforcer() whose SQLAlchemy adapter
    # points at the unrelated global SQLite URL. We inject our own enforcer.
    @asynccontextmanager
    async def noop_lifespan(_app):
        yield

    app.router.lifespan_context = noop_lifespan

    async def override_get_db():
        async with test_env.factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async def fake_decode(token: str):
        return {
            "sub": test_env.owner_user,
            "tenant_id": test_env.tenant_id,
            "email": "owner@example.com",
        }

    with patch.object(casbin_mod, "get_enforcer", return_value=test_env.enforcer), \
         patch.object(deps_mod, "decode_token", new=AsyncMock(side_effect=fake_decode)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

    app.dependency_overrides.clear()
