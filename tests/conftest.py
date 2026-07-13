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
# Settings used by the new local-auth code paths.
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("SALT_ROUNDS", "4")  # keep tests fast

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
        ("agents", "delete"), ("agents", "export"),
        ("conversations", "read"), ("conversations", "create"),
        ("conversations", "update"), ("conversations", "delete"),
        ("conversations", "chat"),
        ("users", "read"), ("users", "create"), ("users", "update"), ("users", "delete"),
        ("roles", "read"), ("roles", "create"), ("roles", "update"), ("roles", "delete"),
        ("settings", "read"), ("settings", "update"),
        ("api_tokens", "read"), ("api_tokens", "create"), ("api_tokens", "delete"),
        ("customers", "read"), ("customers", "create"), ("customers", "update"), ("customers", "delete"),
        ("customers", "export"),
    ]:
        e.add_policy("owner", tenant_id, obj, act)
    # admin: manage users + read-mostly elsewhere (no agent/customer delete).
    for obj, act in [
        ("agents", "read"), ("agents", "create"), ("agents", "update"),
        ("agents", "export"),
        ("conversations", "read"), ("conversations", "create"),
        ("conversations", "chat"),
        ("users", "read"), ("users", "create"), ("users", "update"),
        ("roles", "read"),
        ("settings", "read"), ("settings", "update"),
        ("api_tokens", "read"), ("api_tokens", "create"), ("api_tokens", "delete"),
        ("customers", "read"), ("customers", "create"), ("customers", "update"),
        ("customers", "export"),
    ]:
        e.add_policy("admin", tenant_id, obj, act)
    for obj, act in [
        ("agents", "read"), ("conversations", "read"),
        ("conversations", "create"), ("conversations", "chat"),
        ("roles", "read"),
        ("customers", "read"),
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
    from app.models import (  # noqa: F401
        agent,
        api_token,
        customer,
        group,
        llm_config,
        log,
        message,
        rbac,
        security,
        tenant,
    )

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

    # The owner's User + UserTenant rows must exist in the DB: get_current_user
    # re-validates account state and membership on every request.
    from app.models.tenant import Tenant, User, UserTenant

    async with factory() as session:
        session.add(Tenant(id=tenant_id, name="Test Tenant"))
        session.add(User(id=owner_user, email="owner@example.com", status="active"))
        session.add(UserTenant(user_id=owner_user, tenant_id=tenant_id, role="owner"))
        await session.commit()

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


async def _build_client(
    test_env: _TestEnv,
    *,
    user_id: str,
    email: str,
    role: str,
    platform_role: str | None = None,
) -> AsyncIterator[AsyncClient]:
    """Build an AsyncClient impersonating a user with a given tenant-scoped role.

    Seeds a fresh User + UserTenant(row=role) and binds the same role in casbin
    (the default policies for owner/admin/member are already seeded by
    ``_make_casbin``). The JWT is mocked so the impersonated identity flows
    through ``get_current_user`` unchanged.
    """
    from contextlib import asynccontextmanager

    from app.api import deps as deps_mod
    from app.core import casbin_enforcer as casbin_mod
    from app.core.database import get_db
    from app.main import create_app
    from app.models.tenant import User, UserTenant

    # Seed the impersonated user + membership (get_current_user re-validates
    # account state + membership on every request).
    async with test_env.factory() as session:
        session.add(User(id=user_id, email=email, status="active"))
        session.add(UserTenant(user_id=user_id, tenant_id=test_env.tenant_id, role=role))
        await session.commit()

    # Bind the role in casbin (grouping policy: user → role in this tenant).
    test_env.enforcer.add_role_for_user_in_domain(user_id, role, test_env.tenant_id)

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
        # No ``jti`` on the mocked token: get_current_user only consults the
        # sessions table when a jti is present, so the mock never trips the
        # revocation check.
        claims: dict = {
            "sub": user_id,
            "tenant_id": test_env.tenant_id,
            "email": email,
        }
        if platform_role is not None:
            claims["platform_role"] = platform_role
        return claims

    with patch.object(casbin_mod, "get_enforcer", return_value=test_env.enforcer), \
         patch.object(deps_mod, "decode_token", new=AsyncMock(side_effect=fake_decode)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def app_client(test_env: _TestEnv) -> AsyncIterator[AsyncClient]:
    """FastAPI test client wired to the test engine, seeded casbin, mock JWT.

    Impersonates the tenant owner (full users:* permissions). The owner's
    User/UserTenant rows are seeded by ``test_env`` itself, so unlike
    ``_build_client`` (used for admin/member) this fixture does NOT re-seed.
    """
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
        # No ``jti`` on the mocked token: get_current_user only consults the
        # sessions table when a jti is present, so the mock never trips the
        # revocation check. account-state/membership checks use the seeded rows.
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


@pytest_asyncio.fixture
async def tenant_admin_client(test_env: _TestEnv) -> AsyncIterator[AsyncClient]:
    """Impersonates a tenant admin (users:read/create/update, NO delete)."""
    async for client in _build_client(
        test_env,
        user_id=f"admin-{uuid.uuid4().hex}",
        email="admin@example.com",
        role="admin",
    ):
        yield client


@pytest_asyncio.fixture
async def member_client(test_env: _TestEnv) -> AsyncIterator[AsyncClient]:
    """Impersonates a plain member (no users:* permissions at all)."""
    async for client in _build_client(
        test_env,
        user_id=f"member-{uuid.uuid4().hex}",
        email="member@example.com",
        role="member",
    ):
        yield client


@pytest_asyncio.fixture
async def super_admin_client(test_env: _TestEnv) -> AsyncIterator[AsyncClient]:
    """Like ``app_client`` but the mocked token has ``platform_role=super_admin``
    and the DB has a second tenant with an extra user, so cross-tenant tests work."""
    from contextlib import asynccontextmanager

    from app.api import deps as deps_mod
    from app.core import casbin_enforcer as casbin_mod
    from app.core.database import get_db
    from app.main import create_app

    # Seed a second tenant + user so cross-tenant queries have data.
    from app.models.tenant import Tenant, User, UserTenant

    other_tenant_id = f"tnt-other-{uuid.uuid4().hex}"
    async with test_env.factory() as session:
        session.add(Tenant(id=other_tenant_id, name="Other Tenant"))
        session.add(User(id="cross-user", email="cross@example.com", status="active"))
        session.add(UserTenant(user_id="cross-user", tenant_id=other_tenant_id, role="member"))
        await session.commit()

    # Mark the owner as a super admin.
    async with test_env.factory() as session:
        user = await session.get(User, test_env.owner_user)
        if user is not None:
            user.platform_role = "super_admin"
            await session.commit()

    app = create_app()

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
            "platform_role": "super_admin",
        }

    with patch.object(casbin_mod, "get_enforcer", return_value=test_env.enforcer), \
         patch.object(deps_mod, "decode_token", new=AsyncMock(side_effect=fake_decode)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def hq_staff_client(test_env: _TestEnv) -> AsyncIterator[AsyncClient]:
    """Impersonates a platform ``hq_staff`` user.

    hq_staff is the HQ read-only viewer: any read is allowed (check() short-
    circuits on ``hq_staff`` + ``read``), writes fall through to casbin. We
    bind the impersonated user to the ``member`` tenant role (not owner) so its
    casbin grants are minimal — this faithfully reproduces a real HQ employee
    who has NO store-side business role. Member holds ``customers:read`` but
    not create/update/delete, so hq_staff's write attempts are correctly 403.

    A second tenant is seeded so cross-tenant read assertions have data to see.
    """
    from app.models.tenant import Tenant

    other_tenant_id = f"tnt-other-{uuid.uuid4().hex}"
    async with test_env.factory() as session:
        session.add(Tenant(id=other_tenant_id, name="Other Tenant"))
        await session.commit()

    async for client in _build_client(
        test_env,
        user_id=f"hq-{uuid.uuid4().hex}",
        email="hq@example.com",
        role="member",
        platform_role="hq_staff",
    ):
        yield client


@pytest_asyncio.fixture
async def app_client_real_auth(test_env: _TestEnv) -> AsyncIterator[AsyncClient]:
    """Like ``app_client`` but with REAL JWT verification (no decode_token mock).

    Used by tests that exercise the local-login → /me → /sessions round-trip
    end-to-end. The owner still authenticates via the ``fake`` bearer for the
    *setup* calls (user creation) by stubbing decode_token — but this fixture
    is intended for the calls that present a real minted token. To keep setup
    simple, callers create users via db_session directly.
    """
    from contextlib import asynccontextmanager

    from app.core import casbin_enforcer as casbin_mod
    from app.core.database import get_db
    from app.main import create_app

    app = create_app()

    @asynccontextmanager
    async def noop_lifespan(_app):
        yield

    app.router.lifespan_context = noop_lifespan

    async def override_get_db():
        async with test_env.factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    with patch.object(casbin_mod, "get_enforcer", return_value=test_env.enforcer):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

    app.dependency_overrides.clear()
