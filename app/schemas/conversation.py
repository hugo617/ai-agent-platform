"""Pydantic schemas for conversation / chat DTOs."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    agent_id: str
    title: str | None = None
    # Optional customer attribution (Token 费用管理系列 3/4). Nullable: not
    # every conversation is tied to a customer (staff internal queries).
    customer_id: str | None = None


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    agent_id: str
    tenant_id: str
    user_id: str
    title: str | None = None
    customer_id: str | None = None
    created_at: datetime
    updated_at: datetime


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
    # Optional customer attribution: set when a store staff starts a chat
    # while serving a specific customer. Only takes effect when creating a
    # NEW conversation (ignored if conversation_id is provided). Token 费用
    # 管理系列 3/4 (customer-conversation-link).
    customer_id: str | None = None
