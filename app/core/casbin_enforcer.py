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
    """
    sync_url = settings.database_url.replace("+psycopg", "")
    adapter = Adapter(sync_url)
    return casbin.Enforcer(settings.casbin_model_path, adapter)


# A single lock is enough — pycasbin is not reentrant across policy mutations.
_enforcer_lock = Lock()


def enforcer_lock() -> Lock:
    """Return the lock used to serialize policy mutations."""
    return _enforcer_lock
