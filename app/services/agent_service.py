"""Agent service — CRUD over agents, all operations scoped by tenant + permission."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.agent_specialist import AgentSpecialist
from app.repositories.agent import AgentRepository
from app.repositories.agent_specialist import AgentSpecialistRepository
from app.schemas.agent import AgentCreate, AgentRead, AgentStatistics, AgentUpdate
from app.services.errors import BizError, NotFoundError
from app.services.permission_service import permission_service

# ``AgentSpecialist`` is used inside ``_specialist_map`` (a typed query). The
# top-level import above is the single source — no local re-import needed.


class AgentService:
    OBJECT = "agents"

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = AgentRepository(db)
        self.specialists = AgentSpecialistRepository(db)

    async def _owned(self, agent_id: str, tenant_id: str) -> Agent:
        agent = await self.repo.get_for_tenant(agent_id, tenant_id)
        if agent is None:
            raise NotFoundError(f"agent {agent_id} not found in tenant {tenant_id}")
        return agent

    async def _specialist_map(
        self, tenant_id: str
    ) -> dict[str, list[str]]:
        """All orchestrator→[specialist_id] memberships in a tenant.

        One query for the whole list call (avoids N+1 when hydrating
        ``AgentRead.specialist_ids`` for every agent). Only memberships whose
        orchestrator AND specialist both live in this tenant are returned —
        cross-tenant rows cannot exist (attach validates same-tenant), but the
        filter is cheap defense-in-depth.
        """
        stmt = (
            select(AgentSpecialist.orchestrator_id, AgentSpecialist.specialist_id)
            .join(Agent, Agent.id == AgentSpecialist.specialist_id)
            .where(Agent.tenant_id == tenant_id)
        )
        rows = (await self.db.execute(stmt)).all()
        mapping: dict[str, list[str]] = {}
        for orch_id, spec_id in rows:
            mapping.setdefault(orch_id, []).append(spec_id)
        return mapping

    def _to_read(self, agent: Agent, specialist_map: dict[str, list[str]] | None) -> AgentRead:
        """Build AgentRead, attaching specialist_ids when a map is provided."""
        read = AgentRead.model_validate(agent)
        if specialist_map is not None:
            read.specialist_ids = specialist_map.get(agent.id, [])
        return read

    async def list(
        self,
        user_id: str,
        tenant_id: str,
        platform_role: str | None = None,
        *,
        search: str | None = None,
    ) -> list[AgentRead]:
        """List the tenant's agents, optionally narrowed by a name search.

        Mirrors the users list behaviour: ``search`` is a case-insensitive
        substring on the agent name; empty/None returns everything. Stays
        tenant-scoped (the original semantics) — ``tenant_id`` filtering lives
        in the repository, so multi-tenant isolation cannot be forgotten.
        """
        await permission_service.require(
            user_id, tenant_id, self.OBJECT, "read", platform_role=platform_role
        )
        kw = (search or "").strip() or None
        if kw is None:
            agents = await self.repo.list_for_tenant(tenant_id)
        else:
            agents = await self.repo.search_for_tenant(
                keyword=kw, tenant_id=tenant_id, limit=100
            )
        specialist_map = await self._specialist_map(tenant_id)
        return [self._to_read(a, specialist_map) for a in agents]

    async def statistics(
        self,
        user_id: str,
        tenant_id: str,
        platform_role: str | None = None,
    ) -> AgentStatistics:
        """Agent count for the dashboard card.

        Store users count their tenant's agents; super_admin counts every
        tenant's agents. Agents carry no status column, so ``active`` mirrors
        ``total`` (kept for a consistent card shape across entities).
        """
        is_super_admin = platform_role == "super_admin"
        if not is_super_admin:
            await permission_service.require(
                user_id, tenant_id, self.OBJECT, "read", platform_role=platform_role
            )
        total = (
            await self.repo.count_all()
            if is_super_admin
            else await self.repo.count_for_tenant(tenant_id)
        )
        return AgentStatistics(total=total, active=total)

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
            is_orchestrator=payload.is_orchestrator,
            specialty=payload.specialty,
        )
        await self.repo.add(agent)
        await self.db.commit()
        return self._to_read(agent, None)

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
        specialist_map = await self._specialist_map(tenant_id)
        return self._to_read(agent, specialist_map)

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
        specialist_map = await self._specialist_map(tenant_id)
        return self._to_read(agent, specialist_map)

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
        # Soft delete: hard-deleting would CASCADE-delete the agent's
        # Conversations (agent_id FK) and SET NULL its UsageEvents, destroying
        # all history. Soft-delete keeps the row so history stays joinable;
        # every read in AgentRepository filters is_deleted=False.
        agent.is_deleted = True
        agent.deleted_at = datetime.now(UTC)
        await self.db.flush()
        await self.db.commit()

    # ------------------------------------------- orchestration (priority 58)
    #
    async def list_specialists(
        self,
        user_id: str,
        tenant_id: str,
        orchestrator_id: str,
        platform_role: str | None = None,
    ) -> list[AgentRead]:
        """The specialist Agents attached to an orchestrator.

        Tenant-scoped: the orchestrator must live in ``tenant_id`` (enforced
        via ``_owned`` which 404s on cross-tenant). ``list_specialist_agents``
        re-checks each specialist's tenant in the JOIN, defense-in-depth.
        """
        await permission_service.require(
            user_id, tenant_id, self.OBJECT, "read", platform_role=platform_role
        )
        await self._owned(orchestrator_id, tenant_id)
        agents = await self.specialists.list_specialist_agents(
            orchestrator_id, tenant_id
        )
        return [self._to_read(a, None) for a in agents]

    async def attach_specialist(
        self,
        user_id: str,
        tenant_id: str,
        orchestrator_id: str,
        specialist_id: str,
        platform_role: str | None = None,
    ) -> None:
        """Attach a specialist Agent to an orchestrator.

        Validates: both agents in the same tenant, the orchestrator is
        actually an orchestrator, the specialist is NOT an orchestrator (no
        nesting chains), not self-attach, and not already attached. Every
        failure maps to a 400 (BizError) or 404 (NotFoundError).
        """
        await permission_service.require(
            user_id, tenant_id, self.OBJECT, "update", platform_role=platform_role
        )
        orchestrator = await self._owned(orchestrator_id, tenant_id)
        if not orchestrator.is_orchestrator:
            raise BizError("目标 Agent 未开启编排器功能")
        if orchestrator_id == specialist_id:
            raise BizError("不能将 Agent 挂载到自身")
        specialist = await self._owned(specialist_id, tenant_id)
        if specialist.is_orchestrator:
            # Disallow chaining orchestrators (A routes to B routes to C) to
            # keep the routing graph acyclic and debuggable.
            raise BizError("不能将编排器 Agent 挂载为 specialist(禁止链式编排)")
        if await self.specialists.exists(orchestrator_id, specialist_id):
            raise BizError("该 specialist 已挂载")
        await self.specialists.attach(orchestrator_id, specialist_id)
        await self.db.commit()

    async def detach_specialist(
        self,
        user_id: str,
        tenant_id: str,
        orchestrator_id: str,
        specialist_id: str,
        platform_role: str | None = None,
    ) -> None:
        await permission_service.require(
            user_id, tenant_id, self.OBJECT, "update", platform_role=platform_role
        )
        await self._owned(orchestrator_id, tenant_id)
        removed = await self.specialists.detach(orchestrator_id, specialist_id)
        if not removed:
            raise NotFoundError(
                f"specialist {specialist_id} not attached to {orchestrator_id}"
            )
        await self.db.commit()
