"""API token service — issue, verify (auth bypass), list (masked), revoke.

This is the heart of the AtoA surface. The key invariant: the plaintext token
is produced **only** by :meth:`issue` and returned **once**; everything else
(:meth:`verify`, :meth:`list_for_tenant`, :meth:`revoke`) works off the stored
Fernet ciphertext. ``verify`` is called from ``deps._resolve_api_token`` on
every ``ahp_``-prefixed request and returns a :class:`ResolvedToken` carrying
just the issuer identity — never the token itself.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import API_TOKEN_PREFIX, API_TOKEN_PREFIX_LEN
from app.core import crypto
from app.models.api_token import ApiToken
from app.repositories.api_token import ApiTokenRepository
from app.schemas.api_token import (
    ApiTokenCreate,
    ApiTokenCreateResponse,
    ApiTokenRead,
)
from app.services.errors import NotFoundError
from app.services.permission_service import permission_service

OBJECT = "api_tokens"
ACT_MANAGE = "manage"


@dataclass
class ResolvedToken:
    """The identity resolved from a presented API token (internal, auth-only)."""

    user_id: str
    tenant_id: str


def _to_read(row: ApiToken) -> ApiTokenRead:
    return ApiTokenRead(
        id=row.id,
        name=row.name,
        token_prefix=row.token_prefix,
        token_type=row.token_type,
        scopes=list(row.scopes),
        last_used_at=row.last_used_at,
        expires_at=row.expires_at,
        is_active=row.is_active,
        created_at=row.created_at,
    )


def _extract_prefix(token: str) -> str:
    """The indexed lookup key for a plaintext token (prefix + first chars)."""
    return token[: API_TOKEN_PREFIX_LEN + len(API_TOKEN_PREFIX)]


class ApiTokenService:
    async def issue(
        self,
        db: AsyncSession,
        user_id: str,
        tenant_id: str,
        payload: ApiTokenCreate,
        platform_role: str | None = None,
    ) -> ApiTokenCreateResponse:
        """Create a token and return its plaintext exactly once."""
        await permission_service.require(
            user_id, tenant_id, OBJECT, ACT_MANAGE, platform_role=platform_role
        )
        plaintext = API_TOKEN_PREFIX + secrets.token_urlsafe(32)
        prefix = _extract_prefix(plaintext)
        row = ApiToken(
            tenant_id=tenant_id,
            created_by_user_id=user_id,
            name=payload.name,
            token_type="pat",
            token_hash=crypto.encrypt(plaintext),
            token_prefix=prefix,
            scopes=list(payload.scopes),
            expires_at=payload.expires_at,
        )
        repo = ApiTokenRepository(db)
        await repo.add(row)
        await db.commit()
        await db.refresh(row)
        return ApiTokenCreateResponse(
            token=plaintext,
            token_id=row.id,
            name=row.name,
            token_prefix=row.token_prefix,
            scopes=list(row.scopes),
            expires_at=row.expires_at,
            created_at=row.created_at,
        )

    async def verify(self, db: AsyncSession, token: str) -> ResolvedToken | None:
        """Resolve a presented ``ahp_`` token to its issuer identity, or None.

        Called from the auth bypass on every API-token request. Uses the indexed
        prefix to find candidates, decrypts each to compare, enforces
        active/undeleted/expiry, and refreshes ``last_used_at`` on a hit.
        """
        if not token.startswith(API_TOKEN_PREFIX):
            return None
        prefix = _extract_prefix(token)
        repo = ApiTokenRepository(db)
        candidates = await repo.find_by_prefix(prefix)
        now = datetime.now(UTC)
        for row in candidates:
            try:
                if crypto.decrypt(row.token_hash) != token:
                    continue
            except Exception:  # noqa: BLE001 - ciphertext tampered / key rotated
                continue
            if row.expires_at is not None:
                # SQLite strips tzinfo on read-back; assume naive values are UTC
                # (Postgres with DateTime(timezone=True) returns aware values).
                exp = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(
                    tzinfo=UTC
                )
                if exp <= now:
                    return None
            await repo.update_last_used(row.id)
            await db.commit()
            return ResolvedToken(user_id=row.created_by_user_id, tenant_id=row.tenant_id)
        return None

    async def list_for_tenant(
        self,
        db: AsyncSession,
        user_id: str,
        tenant_id: str,
        platform_role: str | None = None,
    ) -> list[ApiTokenRead]:
        await permission_service.require(
            user_id, tenant_id, OBJECT, ACT_MANAGE, platform_role=platform_role
        )
        rows = await ApiTokenRepository(db).list_for_tenant(tenant_id)
        # Mask revoked/deleted tokens out of the default listing.
        return [_to_read(r) for r in rows if not r.is_deleted]

    async def revoke(
        self,
        db: AsyncSession,
        user_id: str,
        tenant_id: str,
        token_id: str,
        platform_role: str | None = None,
    ) -> None:
        await permission_service.require(
            user_id, tenant_id, OBJECT, ACT_MANAGE, platform_role=platform_role
        )
        repo = ApiTokenRepository(db)
        row = await repo.get_for_tenant(token_id, tenant_id)
        if row is None or row.is_deleted:
            raise NotFoundError(f"api token {token_id} not found in tenant {tenant_id}")
        row.is_active = False
        row.is_deleted = True
        await db.flush()
        await db.commit()


api_token_service = ApiTokenService()
