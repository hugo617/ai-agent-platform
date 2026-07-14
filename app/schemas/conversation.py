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
    # conversation-management fields (priority 50). tags defaults to [] so
    # legacy rows (and the server default '[]') round-trip as an empty list.
    tags: list[str] = Field(default_factory=list)
    is_pinned: bool = False
    is_starred: bool = False
    created_at: datetime
    updated_at: datetime


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    role: str
    content: str
    created_at: datetime


class ConversationStatistics(BaseModel):
    """Aggregate conversation counts for the dashboard card.

    ``total`` = all-time conversations in scope; ``last_7d`` / ``last_30d`` are
    rolling windows on ``created_at`` (when the conversation started), matching
    the plan's store/HQ card shape.
    """

    total: int
    last_7d: int
    last_30d: int


# ------- conversation-management request bodies (priority 50) -------


class ConversationTitleUpdate(BaseModel):
    """Body of PATCH /conversations/{id}/title — rename a conversation."""

    title: str = Field(..., min_length=1, max_length=255)


class TagAdd(BaseModel):
    """Body of POST /conversations/{id}/tags — append one tag string."""

    tag: str = Field(..., min_length=1, max_length=64)


class PinUpdate(BaseModel):
    """Body of PATCH /conversations/{id}/pin — set the pinned flag."""

    pinned: bool


class StarUpdate(BaseModel):
    """Body of PATCH /conversations/{id}/star — set the starred flag."""

    starred: bool


class BatchDelete(BaseModel):
    """Body of POST /conversations/batch-delete — a list of conversation ids.

    The service verifies every id belongs to the caller (same user within the
    tenant); any id that does not is rejected rather than silently skipped.
    """

    conversation_ids: list[str] = Field(..., min_length=1)


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
