"""Agent endpoints — CRUD, all guarded by casbin permissions."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.core.database import get_db
from app.schemas.agent import AgentCreate, AgentRead, AgentStatistics, AgentUpdate
from app.services.agent_service import AgentService
from app.services.errors import NotFoundError

router = APIRouter(prefix="/agents", tags=["agents"])


def _http_exc(e: ValueError) -> HTTPException:
    """Map a service ValueError to the right HTTP status by exception type."""
    if isinstance(e, NotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/",
    response_model=list[AgentRead],
    dependencies=[Depends(require_permission("agents", "read"))],
)
async def list_agents(
    search: str | None = Query(
        default=None, description="Substring match on agent name (ILIKE)"
    ),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AgentRead]:
    """List this tenant's agents, optionally filtered by a name search."""
    service = AgentService(db)
    return await service.list(
        user.user_id,
        user.tenant_id,
        platform_role=user.platform_role,
        search=search,
    )


@router.get(
    "/statistics",
    response_model=AgentStatistics,
    dependencies=[Depends(require_permission("agents", "read"))],
)
async def agent_statistics(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentStatistics:
    """Aggregate agent counts for the dashboard card.

    Store users count their tenant's agents; super_admin counts every tenant's
    agents (the service splits on ``platform_role``).
    """
    service = AgentService(db)
    return await service.statistics(
        user.user_id, user.tenant_id, platform_role=user.platform_role
    )


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
    return await service.create(
        user.user_id, user.tenant_id, payload, platform_role=user.platform_role
    )


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
        return await service.get(
            user.user_id, user.tenant_id, agent_id, platform_role=user.platform_role
        )
    except ValueError as e:
        raise _http_exc(e) from e


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
        return await service.update(
            user.user_id,
            user.tenant_id,
            agent_id,
            payload,
            platform_role=user.platform_role,
        )
    except ValueError as e:
        raise _http_exc(e) from e


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
        await service.delete(
            user.user_id, user.tenant_id, agent_id, platform_role=user.platform_role
        )
    except ValueError as e:
        raise _http_exc(e) from e
