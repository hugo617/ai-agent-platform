"""Global API rate limiting (rate-limit-login-lockout slice 02).

Assembly contract (see plan §4.6):

- ``limiter`` is a **module-level singleton**, NOT a per-create_app factory.
  Route decorators (``@limiter.limit`` on POST /auth/login) bind the instance
  at import time; a factory-fresh Limiter hung on ``app.state.limiter`` would
  leave the decorator and the middleware counting into two separate storages.
- ``rate_limit_key`` is the default key function: a *verified* bearer token
  yields ``user:{sub}``; anything else (no token, failed verification, or an
  ``ahp_`` PAT — resolved lazily elsewhere and deliberately not DB-looked-up
  here) falls back to the client IP. Verification must come from
  ``app.core.security.decode_token_sync`` — importing from ``app.api.deps``
  would make tests' ``decode_token`` mocks silently rewrite every key, and an
  unverified decode would let an attacker rotate forged ``sub`` claims to
  dodge the per-user quota entirely.
- ``RateLimitMiddleware`` short-circuits the probe/docs exemption paths before
  slowapi sees the request (slowapi has no ``exempt_paths`` constructor option
  and its ``@limiter.exempt`` decorator cannot reach /docs or /health, which
  are defined inside ``create_app``). It subclasses ``SlowAPIMiddleware``
  rather than poking slowapi internals.
"""

from slowapi import Limiter
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.core.config import settings
from app.core.security import TokenError, decode_token_sync

# Long-lived API tokens (agenthub platform) carry this prefix. They are
# resolved through a separate DB-backed bypass in get_current_user, so the
# rate-limit key_func deliberately treats them as anonymous (IP-keyed) instead
# of paying a DB lookup per request.
_PAT_PREFIX = "ahp_"


def rate_limit_key(request: Request) -> str:
    """Default quota key: verified token subject, else client IP.

    ``user:{sub}`` is namespaced so a subject can never collide with an IP
    address in the limiter's shared keyspace.
    """
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if token and not token.startswith(_PAT_PREFIX):
            try:
                claims = decode_token_sync(token)
            except TokenError:
                pass  # garbage/forged token → IP bucket, never a user bucket
            else:
                sub = claims.get("sub")
                if sub:
                    return f"user:{sub}"
    return get_remote_address(request)


limiter = Limiter(
    key_func=rate_limit_key,
    # Callable so the quota string is read from settings at assembly time;
    # tests override it via env before this module's first import.
    default_limits=[lambda: settings.rate_limit_default],
    headers_enabled=True,
    enabled=settings.rate_limit_enabled,
)


class RateLimitMiddleware(SlowAPIMiddleware):
    """SlowAPIMiddleware + exempt-path short-circuit.

    Exempt paths (/health, /ready, /metrics, docs) skip rate limiting entirely
    (a 429 on a K8s probe would restart the pod); everything else goes through
    the unchanged SlowAPIMiddleware behavior (default tier for undecorated
    routes; routes with a @limiter.limit decorator are handled by the decorator
    itself).
    """

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if request.url.path in settings.rate_limit_exempt_paths_set:
            return await call_next(request)
        return await super().dispatch(request, call_next)
