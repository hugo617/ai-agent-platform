"""Auth endpoints — who am I? (login itself is delegated to Logto)."""

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, get_current_user
from app.schemas.auth import MeResponse
from app.services.permission_service import permission_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUser = Depends(get_current_user)) -> MeResponse:
    roles = await permission_service.get_roles_for_user_in_domain(
        user.user_id, user.tenant_id
    )
    return MeResponse(
        user_id=user.user_id,
        tenant_id=user.tenant_id,
        email=user.email,
        roles=roles,
    )
