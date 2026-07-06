"""Agent endpoints — CRUD, all guarded by casbin permissions."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.core.database import get_db
from app.schemas.agent import AgentCreate, AgentRead, AgentUpdate
from app.services.agent_service import AgentService

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get(
    "/",
    response_model=list[AgentRead],
    dependencies=[Depends(require_permission("agents", "read"))],
)
async def list_agents(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AgentRead]:
    service = AgentService(db)
    return await service.list(user.user_id, user.tenant_id)


@router.post(
    "/",
    response_model=AgentRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("agents", "create"))],
)
async def create_agent(
    payload: AgentCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentRead:
    service = AgentService(db)
    return await service.create(user.user_id, user.tenant_id, payload)


@router.get(
    "/{agent_id}",
    response_model=AgentRead,
    dependencies=[Depends(require_permission("agents", "read"))],
)
async def get_agent(
    agent_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentRead:
    service = AgentService(db)
    try:
        return await service.get(user.user_id, user.tenant_id, agent_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.patch(
    "/{agent_id}",
    response_model=AgentRead,
    dependencies=[Depends(require_permission("agents", "update"))],
)
async def update_agent(
    agent_id: str,
    payload: AgentUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentRead:
    service = AgentService(db)
    try:
        return await service.update(user.user_id, user.tenant_id, agent_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.delete(
    "/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("agents", "delete"))],
)
async def delete_agent(
    agent_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = AgentService(db)
    try:
        await service.delete(user.user_id, user.tenant_id, agent_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
