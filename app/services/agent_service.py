"""Agent service — CRUD over agents, all operations scoped by tenant + permission."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.repositories.agent import AgentRepository
from app.schemas.agent import AgentCreate, AgentRead, AgentUpdate
from app.services.errors import NotFoundError
from app.services.permission_service import permission_service


class AgentService:
    OBJECT = "agents"

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = AgentRepository(db)

    async def _owned(self, agent_id: str, tenant_id: str) -> Agent:
        agent = await self.repo.get_for_tenant(agent_id, tenant_id)
        if agent is None:
            raise NotFoundError(f"agent {agent_id} not found in tenant {tenant_id}")
        return agent

    async def list(
        self, user_id: str, tenant_id: str, platform_role: str | None = None
    ) -> list[AgentRead]:
        await permission_service.require(
            user_id, tenant_id, self.OBJECT, "read", platform_role=platform_role
        )
        agents = await self.repo.list_for_tenant(tenant_id)
        return [AgentRead.model_validate(a) for a in agents]

    async def create(
        self,
        user_id: str,
        tenant_id: str,
        payload: AgentCreate,
        platform_role: str | None = None,
    ) -> AgentRead:
        await permission_service.require(
            user_id, tenant_id, self.OBJECT, "create", platform_role=platform_role
        )
        agent = Agent(
            tenant_id=tenant_id,
            name=payload.name,
            system_prompt=payload.system_prompt,
            model=payload.model,
            description=payload.description,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
            top_p=payload.top_p,
        )
        await self.repo.add(agent)
        await self.db.commit()
        return AgentRead.model_validate(agent)

    async def get(
        self,
        user_id: str,
        tenant_id: str,
        agent_id: str,
        platform_role: str | None = None,
    ) -> AgentRead:
        await permission_service.require(
            user_id, tenant_id, self.OBJECT, "read", platform_role=platform_role
        )
        agent = await self._owned(agent_id, tenant_id)
        return AgentRead.model_validate(agent)

    async def update(
        self,
        user_id: str,
        tenant_id: str,
        agent_id: str,
        payload: AgentUpdate,
        platform_role: str | None = None,
    ) -> AgentRead:
        await permission_service.require(
            user_id, tenant_id, self.OBJECT, "update", platform_role=platform_role
        )
        agent = await self._owned(agent_id, tenant_id)
        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(agent, key, value)
        await self.db.flush()
        await self.db.commit()
        return AgentRead.model_validate(agent)

    async def delete(
        self,
        user_id: str,
        tenant_id: str,
        agent_id: str,
        platform_role: str | None = None,
    ) -> None:
        await permission_service.require(
            user_id, tenant_id, self.OBJECT, "delete", platform_role=platform_role
        )
        agent = await self._owned(agent_id, tenant_id)
        await self.repo.delete(agent)
        await self.db.commit()
