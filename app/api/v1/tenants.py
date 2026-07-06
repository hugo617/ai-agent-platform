"""Tenant endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user
from app.core.database import get_db
from app.schemas.tenant import TenantCreate, TenantRead
from app.services.tenant_service import TenantService

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("/", response_model=TenantRead, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    payload: TenantCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TenantRead:
    service = TenantService(db)
    return await service.create_tenant(user.user_id, payload, owner_email=user.email)


@router.get("/", response_model=list[TenantRead])
async def list_my_tenants(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TenantRead]:
    service = TenantService(db)
    tenants = await service.list_user_tenants(user.user_id)
    if not tenants:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="you have no tenants; create one first",
        )
    return tenants
