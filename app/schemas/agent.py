"""Pydantic schemas for agent DTOs."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AgentBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    system_prompt: str = ""
    model: str = "deepseek-chat"
    # Inference parameters. ``temperature`` always has a value (0.7 general
    # default); ``max_tokens``/``top_p`` are None = "don't forward to the LLM,
    # use the provider default". Bounds match common OpenAI-compatible APIs.
    description: str = ""
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int | None = Field(None, ge=1, le=32768)
    top_p: float | None = Field(None, ge=0.0, le=1.0)
    # Orchestration (priority 58). ``is_orchestrator=True`` turns this Agent
    # into a supervisor that routes to its specialists; ``specialty`` is a
    # free-text role description the supervisor LLM reads when routing — only
    # meaningful for specialists.
    is_orchestrator: bool = False
    specialty: str | None = None


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    system_prompt: str | None = None
    model: str | None = None
    description: str | None = None
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(None, ge=1, le=32768)
    top_p: float | None = Field(None, ge=0.0, le=1.0)
    is_orchestrator: bool | None = None
    specialty: str | None = None


class AgentRead(AgentBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    tenant_id: str
    created_at: datetime
    # Specialist Agent ids attached to this orchestrator (empty for regular
    # agents). Populated by the service layer — the ORM row itself has no such
    # attribute, so default to [] when not supplied (model_validate fills it
    # via the default because the Agent model lacks the attr only if we pass
    # it explicitly; we always set it from the service layer).
    specialist_ids: list[str] = Field(default_factory=list)


class AgentStatistics(BaseModel):
    """Aggregate agent counts for the dashboard card.

    ``total`` = all agents in scope; ``active`` mirrors the other entity stats
    for a consistent card shape (agents have no status column, so ``active``
    always equals ``total`` — kept in the payload so the dashboard renders one
    shape regardless of entity).
    """

    total: int
    active: int
