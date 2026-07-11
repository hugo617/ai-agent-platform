"""API token repository (tenant-scoped).

The auth-time lookup (:meth:`find_by_prefix`) is indexed by ``token_prefix``:
``get_current_user`` extracts the prefix from the presented ``ahp_`` token and
narrows the candidate rows to a handful before decrypting each to compare. This
keeps verification O(prefix fanout) rather than a full-table scan.
"""

from datetime import UTC, datetime

from sqlalchemy import select, update

from app.models.api_token import ApiToken
from app.repositories.base import TenantScopedRepository


class ApiTokenRepository(TenantScopedRepository[ApiToken]):
    model = ApiToken

    async def find_by_prefix(self, token_prefix: str) -> list[ApiToken]:
        """Candidate active, non-deleted rows matching a token prefix.

        Used by the auth bypass: the caller decrypts each row's ``token_hash``
        and compares to the presented token. Scoping by prefix keeps this cheap.
        """
        stmt = select(ApiToken).where(
            ApiToken.token_prefix == token_prefix,
            ApiToken.is_active.is_(True),
            ApiToken.is_deleted.is_(False),
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_last_used(self, token_id: str) -> None:
        """Refresh ``last_used_at`` for a token after a successful auth."""
        await self.db.execute(
            update(ApiToken).where(ApiToken.id == token_id).values(last_used_at=datetime.now(UTC))
        )
        await self.db.flush()
