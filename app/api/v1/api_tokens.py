"""API token endpoints — issue, list (masked), revoke, and verify.

Issue/list/revoke require ``api_tokens:manage`` (seeded for owner/admin). The
``/verify`` endpoint only needs an authenticated caller: an external agent
presents its token as a Bearer credential (resolved by the ``ahp_`` bypass in
``get_current_user``) and gets back its identity — this is what ``agenthub
whoami`` calls.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.core.database import get_db
from app.schemas.api_token import (
    ApiTokenCreate,
    ApiTokenCreateResponse,
    ApiTokenRead,
)
from app.services.api_token_service import api_token_service
from app.services.errors import NotFoundError

router = APIRouter(prefix="/api-tokens", tags=["api-tokens"])


def _http_exc(e: ValueError) -> HTTPException:
    """Map a service ValueError to the right HTTP status by exception type."""
    if isinstance(e, NotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "",
    response_model=ApiTokenCreateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("api_tokens", "manage"))],
)
async def issue_token(
    payload: ApiTokenCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiTokenCreateResponse:
    """Issue a new API token. The plaintext token is returned **only here**."""
    return await api_token_service.issue(
        db, user.user_id, user.tenant_id, payload, platform_role=user.platform_role
    )


@router.get(
    "",
    response_model=list[ApiTokenRead],
    dependencies=[Depends(require_permission("api_tokens", "manage"))],
)
async def list_tokens(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ApiTokenRead]:
    """List the caller's tenant tokens (masked — no plaintext, no ciphertext)."""
    return await api_token_service.list_for_tenant(
        db, user.user_id, user.tenant_id, platform_role=user.platform_role
    )


@router.delete(
    "/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("api_tokens", "manage"))],
)
async def revoke_token(
    token_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Revoke (soft-delete) an API token."""
    try:
        await api_token_service.revoke(
            db, user.user_id, user.tenant_id, token_id, platform_role=user.platform_role
        )
    except ValueError as e:
        raise _http_exc(e) from e


@router.get("/verify", response_model=dict)
async def verify_token(
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Confirm the presented credential is valid and return the identity.

    Used by ``agenthub whoami``. Works for both API tokens (``ahp_`` bypass) and
    regular JWTs — it simply echoes back the resolved principal.
    """
    return {"valid": True, "user_id": user.user_id, "tenant_id": user.tenant_id}
