"""Pydantic schemas for conversation / chat DTOs."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    agent_id: str
    title: str | None = None


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    agent_id: str
    tenant_id: str
    user_id: str
    title: str | None = None
    created_at: datetime


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    role: str
    content: str
    created_at: datetime


class ChatRequest(BaseModel):
    """Body of a streaming chat request."""

    agent_id: str
    conversation_id: str | None = None
    message: str = Field(..., min_length=1)
