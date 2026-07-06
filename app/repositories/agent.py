"""Agent repository (tenant-scoped)."""

from app.models.agent import Agent
from app.repositories.base import TenantScopedRepository


class AgentRepository(TenantScopedRepository[Agent]):
    model = Agent
