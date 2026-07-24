"""JWT verification for tokens issued by Logto.

Logto is an OIDC provider. Our API only *verifies* access tokens:
  1. Fetch the signing keys (JWKS) from the Logto issuer.
  2. Validate signature + audience + issuer.
  3. Return the decoded claims.

No login UI lives here — the frontend redirects users to Logto directly.
"""

import time
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient

from app.core.config import settings


class TokenError(Exception):
    """Raised when a token is missing, malformed, or invalid."""


_jwks_client: PyJWKClient | None = None
_jwks_fetched_at: float = 0
_JWKS_TTL = 600  # refresh keys at most every 10 minutes


def _jwks_uri() -> str:  # pragma: no cover — needs a live Logto/dev issuer
    """JWKS endpoint to fetch signing keys from.

    In production this is ``{LOGTO_ISSUER}/jwks``. In development, when the
    issuer points at our own backend (``LOGTO_ISSUER=http://localhost:8000/oidc``),
    we serve the dev key pair at ``/oidc/jwks`` — so the *same* verification
    code path validates both Logto-issued and dev tokens.
    """
    return f"{settings.logto_issuer}/jwks"


def _get_jwks_client() -> PyJWKClient:  # pragma: no cover — needs a live JWKS endpoint
    global _jwks_client, _jwks_fetched_at
    now = time.time()
    if _jwks_client is None or now - _jwks_fetched_at > _JWKS_TTL:
        _jwks_client = PyJWKClient(_jwks_uri())
        _jwks_fetched_at = now
    return _jwks_client


async def decode_token(token: str) -> dict[str, Any]:
    """Verify and decode an access token (local, Logto-issued, or dev-minted).

    Returns the JWT claims payload. Raises ``TokenError`` on any failure.

    Three token kinds flow through here:
      1. **Local** — HS256, ``iss == "local"``, signed with ``JWT_SECRET``.
         Issued by ``POST /api/v1/auth/login`` (username/password login).
      2. **Logto** — RS256, verified against the issuer's JWKS endpoint.
      3. **Dev** — RS256, verified with the in-memory dev RSA key (dev env only).
    """
    if not token:
        raise TokenError("missing token")

    # Peek at the (unverified) payload to dispatch on ``iss``. A local token
    # never touches the JWKS/dev-key path. Any decode error here falls through
    # to the RS256 handling below, which will surface the real failure.
    try:
        unverified = jwt.decode(token, options={"verify_signature": False})
    except jwt.InvalidTokenError:
        unverified = {}
    if unverified.get("iss") == "local":
        return _verify_local_token(token)

    # In dev mode the issuer points at our own backend; fetching JWKS over HTTP
    # would deadlock a single-worker uvicorn, so we use the in-memory dev key.
    if settings.app_env == "development" and settings.logto_issuer.startswith("http://localhost:8000"):  # pragma: no cover - dev env only
        return _verify_with_dev_key(token)

    try:  # pragma: no cover — RS256 path needs a live Logto JWKS endpoint
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token).key
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=settings.logto_audience,
            issuer=settings.logto_issuer,
            options={"require": ["exp", "iat", "iss", "aud"]},
        )
        return payload
    except jwt.ExpiredSignatureError as e:
        raise TokenError("token expired") from e
    except jwt.InvalidTokenError as e:
        raise TokenError(f"invalid token: {e}") from e
    except httpx.HTTPError as e:
        raise TokenError(f"cannot reach issuer: {e}") from e


def _verify_with_dev_key(token: str) -> dict[str, Any]:  # pragma: no cover - dev env only
    """Validate a dev token using the in-memory RSA key pair (no HTTP call)."""
    from app.core.dev_keys import get_dev_keys

    keys = get_dev_keys()
    try:
        payload = jwt.decode(
            token,
            keys.public_pem,
            algorithms=["RS256"],
            audience=settings.logto_audience,
            issuer=settings.logto_issuer,
            options={"require": ["exp", "iat", "iss", "aud"]},
        )
        return payload
    except jwt.ExpiredSignatureError as e:
        raise TokenError("token expired") from e
    except jwt.InvalidTokenError as e:
        raise TokenError(f"invalid token: {e}") from e


def _verify_local_token(token: str) -> dict[str, Any]:
    """Validate a locally-minted HS256 token (``iss == "local"``).

    These tokens are produced by ``POST /api/v1/auth/login``. They carry the
    same claim shape (``sub``, ``tenant_id``, ``email``) as Logto tokens, so
    downstream code in ``deps.get_current_user`` does not care which kind it is.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer="local",
            options={"require": ["exp", "iat", "iss", "sub"]},
        )
        return payload
    except jwt.ExpiredSignatureError as e:
        raise TokenError("token expired") from e
    except jwt.InvalidTokenError as e:
        raise TokenError(f"invalid token: {e}") from e


def extract_subject(claims: dict[str, Any]) -> str:
    """Return the user subject (sub) from claims."""
    sub = claims.get("sub")
    if not sub:
        raise TokenError("token has no subject (sub)")
    return str(sub)


def extract_tenant(claims: dict[str, Any]) -> str | None:
    """Return the tenant id from a custom Logto claim, if present.

    Logto lets you attach custom JWT claims via "Custom JWT" configuration.
    We expect either ``tenant_id`` (custom) or fall back to None, meaning
    the tenant must be resolved from the user→tenant mapping table.
    """
    tenant_id = claims.get("tenant_id")
    return str(tenant_id) if tenant_id else None


def extract_platform_role(claims: dict[str, Any]) -> str | None:
    """Return the platform role from JWT claims, or None for normal users."""
    role = claims.get("platform_role")
    return str(role) if role else None


def extract_customer_id(claims: dict[str, Any]) -> str | None:
    """Return the customer identity from JWT claims, or None.

    A customer-bound token carries a ``customer_id`` custom claim naming the
    global ``Customer`` row the principal acts as (slice 04 — the GET /me/
    bookings endpoint filters on this). Store-staff tokens omit it, so this
    returns None and that endpoint rejects them (403). Mirrors
    ``extract_platform_role`` — a custom Logto JWT claim read verbatim.
    """
    customer_id = claims.get("customer_id")
    return str(customer_id) if customer_id else None
