"""Pydantic schemas for agent DTOs."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AgentBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    system_prompt: str = ""
    model: str = "gpt-4o-mini"


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    system_prompt: str | None = None
    model: str | None = None


class AgentRead(AgentBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    tenant_id: str
    created_at: datetime
