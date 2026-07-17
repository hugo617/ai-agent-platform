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
from dataclasses import dataclass, field
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
from app.services.errors import NotFoundError, ScopeError
from app.services.permission_service import (
    DEFAULT_ADMIN_PERMS,
    DEFAULT_MEMBER_PERMS,
    DEFAULT_OWNER_PERMS,
    permission_service,
)

OBJECT = "api_tokens"
# Fine-grained actions (split from the coarse ``manage`` in
# permission-unified-model): issue→create, list→read, revoke→delete. The router
# guards in api_tokens.py use the same verbs, and these Service-layer requires
# mirror them so the two checks never disagree.
ACT_CREATE = "create"
ACT_READ = "read"
ACT_DELETE = "delete"


@dataclass
class ResolvedToken:
    """The identity resolved from a presented API token (internal, auth-only).

    Carries the scope context (``token_id`` / ``scopes`` / ``scope_mode``) so
    the auth bypass can populate ``current_token_ctx`` for ``check`` to read.
    """

    user_id: str
    tenant_id: str
    token_id: str = ""
    scopes: list[str] = field(default_factory=list)
    scope_mode: str = "full"


def _to_read(row: ApiToken) -> ApiTokenRead:
    return ApiTokenRead(
        id=row.id,
        name=row.name,
        token_prefix=row.token_prefix,
        token_type=row.token_type,
        scopes=list(row.scopes),
        scope_mode=row.scope_mode or "full",
        last_used_at=row.last_used_at,
        expires_at=row.expires_at,
        is_active=row.is_active,
        created_at=row.created_at,
    )


def _extract_prefix(token: str) -> str:
    """The indexed lookup key for a plaintext token (prefix + first chars)."""
    return token[: API_TOKEN_PREFIX_LEN + len(API_TOKEN_PREFIX)]


def _all_known_scope_codes() -> set[str]:
    """Every permission code the platform knows about, as ``"<obj>:<act>"``.

    Used when a ``super_admin`` issues a restricted token: casbin has no
    policy for super_admin (it bypasses via platform_role), so
    ``get_implicit_permissions_for_user`` returns ``[]`` and a naive
    intersection would collapse the token's scopes to the empty set. We
    substitute the full catalogue instead — the token can then request any
    scope that exists, and the live ``check``-time intersection with the
    grantor's CURRENT permissions (which for super_admin is "everything",
    via the bypass) keeps it correct.

    Includes the menu codes (``menu:<code>``) so a super_admin restricted
    token can be scoped to menu visibility too. Without this, a super_admin
    ``full``-mode token (which doesn't read scopes at all) would still work,
    but a super_admin restricted token would silently drop all menu perms.
    """
    codes: set[str] = set()
    for perms in (DEFAULT_OWNER_PERMS, DEFAULT_ADMIN_PERMS, DEFAULT_MEMBER_PERMS):
        for obj, act in perms:
            codes.add(f"{obj}:{act}")
    # Menu perms: DEFAULT_MENU_PERMS is keyed by role → list of menu codes,
    # and the super_admin-only ``menu:tenants`` isn't in any role's list, so
    # pull every menu code from MENU_CN keys (the authoritative menu list).
    from app.services.permission_service import MENU_CN

    for menu_code in MENU_CN:
        codes.add(f"menu:{menu_code}")
    return codes


class ApiTokenService:
    async def issue(
        self,
        db: AsyncSession,
        user_id: str,
        tenant_id: str,
        payload: ApiTokenCreate,
        platform_role: str | None = None,
    ) -> ApiTokenCreateResponse:
        """Create a token and return its plaintext exactly once.

        Scope convergence (AWS STS-style intersection algebra):

            effective_scopes = payload.scopes ∩ grantor_current_permissions

        For ``scope_mode="restricted"`` the token may NEVER exceed the grantor.
        We compute the intersection up front (at issue time) AND again live at
        every ``check`` (the grantor may have been revoked/demoted since
        issue). If the issue-time intersection is empty we refuse — a
        restricted token that can do nothing is a user error, not a silent
        success.

        Super-admin special case: casbin has no policy for super_admin (it
        bypasses via ``platform_role``), so ``get_implicit_permissions_for_user``
        returns ``[]`` and a naive intersection would collapse the scopes to
        empty. Substitute the full catalogue (``_all_known_scope_codes``) —
        the live ``check``-time bypass keeps the token correct.
        """
        await permission_service.require(
            user_id, tenant_id, OBJECT, ACT_CREATE, platform_role=platform_role
        )

        # Converge scopes for restricted mode. Full mode stores the requested
        # scopes verbatim (informational only — check never reads them for
        # full-mode tokens, it falls through to the grantor's current perms).
        if payload.scope_mode == "restricted":
            if platform_role == "super_admin":
                # casbin has no super_admin policy; use the full catalogue.
                grantor_perms = _all_known_scope_codes()
            else:
                implicit = await permission_service.get_implicit_permissions_for_user(
                    user_id, tenant_id
                )
                # casbin returns [sub, dom, obj, act] tuples.
                grantor_perms = {f"{p[2]}:{p[3]}" for p in implicit}
            effective = [s for s in payload.scopes if s in grantor_perms]
            if not effective:
                raise ScopeError(
                    "restricted token 收敛后无可用 scope:请检查授予者权限,"
                    "扩大 scope 范围,或改用 full 模式"
                )
            final_scopes = effective
        else:  # full
            final_scopes = list(payload.scopes)

        plaintext = API_TOKEN_PREFIX + secrets.token_urlsafe(32)
        prefix = _extract_prefix(plaintext)
        row = ApiToken(
            tenant_id=tenant_id,
            created_by_user_id=user_id,
            name=payload.name,
            token_type="pat",
            token_hash=crypto.encrypt(plaintext),
            token_prefix=prefix,
            scopes=final_scopes,
            scope_mode=payload.scope_mode,
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
            scope_mode=row.scope_mode,
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
            return ResolvedToken(
                user_id=row.created_by_user_id,
                tenant_id=row.tenant_id,
                token_id=row.id,
                scopes=list(row.scopes),
                scope_mode=row.scope_mode or "full",
            )
        return None

    async def list_for_tenant(
        self,
        db: AsyncSession,
        user_id: str,
        tenant_id: str,
        platform_role: str | None = None,
    ) -> list[ApiTokenRead]:
        await permission_service.require(
            user_id, tenant_id, OBJECT, ACT_READ, platform_role=platform_role
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
            user_id, tenant_id, OBJECT, ACT_DELETE, platform_role=platform_role
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
