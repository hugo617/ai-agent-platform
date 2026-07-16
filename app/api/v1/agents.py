"""Agent endpoints — CRUD, all guarded by casbin permissions."""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.core.database import get_db
from app.schemas.agent import AgentCreate, AgentRead, AgentStatistics, AgentUpdate
from app.services.agent_service import AgentService

router = APIRouter(prefix="/agents", tags=["agents"])


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
    return await service.get(
        user.user_id, user.tenant_id, agent_id, platform_role=user.platform_role
    )


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
    return await service.update(
        user.user_id,
        user.tenant_id,
        agent_id,
        payload,
        platform_role=user.platform_role,
    )


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
    await service.delete(
        user.user_id, user.tenant_id, agent_id, platform_role=user.platform_role
    )


# ------------------------------------------- orchestration (priority 58)
#
# Specialist attach/detach for orchestrator Agents. These are multi-segment
# paths (/agents/{id}/specialists/...) so they never collide with the
# single-segment /{agent_id} routes above, regardless of declaration order.
@router.get(
    "/{orchestrator_id}/specialists",
    response_model=list[AgentRead],
    dependencies=[Depends(require_permission("agents", "read"))],
)
async def list_orchestrator_specialists(
    orchestrator_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AgentRead]:
    """List the specialist Agents attached to an orchestrator."""
    service = AgentService(db)
    return await service.list_specialists(
        user.user_id,
        user.tenant_id,
        orchestrator_id,
        platform_role=user.platform_role,
    )


@router.post(
    "/{orchestrator_id}/specialists/{specialist_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("agents", "update"))],
)
async def attach_specialist(
    orchestrator_id: str,
    specialist_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Attach a specialist Agent to an orchestrator (idempotent-safe: 400 on dup)."""
    service = AgentService(db)
    await service.attach_specialist(
        user.user_id,
        user.tenant_id,
        orchestrator_id,
        specialist_id,
        platform_role=user.platform_role,
    )


@router.delete(
    "/{orchestrator_id}/specialists/{specialist_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("agents", "update"))],
)
async def detach_specialist(
    orchestrator_id: str,
    specialist_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Detach a specialist Agent from an orchestrator."""
    service = AgentService(db)
    await service.detach_specialist(
        user.user_id,
        user.tenant_id,
        orchestrator_id,
        specialist_id,
        platform_role=user.platform_role,
    )
