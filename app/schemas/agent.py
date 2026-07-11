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


class AgentRead(AgentBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    tenant_id: str
    created_at: datetime
