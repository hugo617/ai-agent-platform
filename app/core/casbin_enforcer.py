"""pycasbin enforcer for multi-tenant authorization.

casbin-sqlalchemy-adapter is synchronous, so we wrap its operations with
``run_in_threadpool`` at the service layer. The enforcer itself is a process-wide
singleton (policies are cached in memory and persisted to the ``casbin_rule``
table by the adapter).
"""

from functools import lru_cache
from threading import Lock

import casbin
from casbin_sqlalchemy_adapter import Adapter

from app.core.config import settings


@lru_cache
def get_enforcer() -> casbin.Enforcer:
    """Build (once) the process-wide synchronous Enforcer backed by PostgreSQL.

    The adapter auto-creates the ``casbin_rule`` table on first use.

    The app's own data layer runs on an async SQLAlchemy driver (``+asyncpg``
    for Postgres in deployment, ``+aiosqlite`` for the in-memory test DB), but
    casbin-sqlalchemy-adapter is sync — it calls ``create_engine`` internally,
    which needs a *sync* driver. We strip the async driver suffix so the URL
    falls back to the default sync driver (psycopg for Postgres, sqlite3 for
    SQLite). Without this, the sync adapter would try to run the async driver
    and every permission check would crash with ``MissingGreenlet`` the first
    time the request path touched a DB relationship under a real async server
    (uvicorn + asyncpg); the sqlite test suite never hit it because tests run
    through a sync-flavoured URL already.
    """
    sync_url = settings.database_url
    for async_suffix in ("+asyncpg", "+aiosqlite", "+psycopg"):
        # ``+psycopg`` is ambiguous (psycopg3 has both sync and async modes),
        # but the app only ever configures it as the sync default, so stripping
        # it is safe and matches the pre-existing behaviour.
        sync_url = sync_url.replace(async_suffix, "")
    adapter = Adapter(sync_url)
    return casbin.Enforcer(settings.casbin_model_path, adapter)


# A single lock is enough — pycasbin is not reentrant across policy mutations.
_enforcer_lock = Lock()


def enforcer_lock() -> Lock:
    """Return the lock used to serialize policy mutations."""
    return _enforcer_lock
