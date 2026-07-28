"""Pydantic schemas for conversation / chat DTOs."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    # composite-chat (priority 72). Defaults to "single" so legacy rows (and
    # the server_default) round-trip as single-agent conversations; Literal
    # tightens the value to prevent typos like "compsite" sneaking in.
    kind: Literal["single", "composite"] = "single"
    created_at: datetime
    updated_at: datetime


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    role: str
    content: str
    status: str = "completed"
    error: str | None = None
    # composite-chat (priority 72). None for ordinary messages; only the
    # assistant turn of a composite conversation carries per-agent fragments.
    fragments: list[dict] | None = None
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


# ------- composite-chat request / response (priority 72) -------
#
# Composite = fan-out + synthesize: ask N agents the same question in parallel,
# then synthesize one answer. Contrast with Supervisor (priority 58), which
# routes to ONE specialist. The request/response are plain JSON (not SSE) —
# composite returns a single synthesized payload, slice 02's composite_query
# produces the fragments, slice 03 wires the endpoint + N+1 UsageEvents.


class CompositeRequest(BaseModel):
    """Body of POST /chat/composite — fan out to N agents, synthesize one answer.

    ``agent_ids`` is de-duplicated (order-preserving) by the endpoint before
    fan-out, so duplicate ids cost no extra tokens. Capped at 8 to bound the
    N+1 token cost and the concurrent LLM pressure (plan §五). ``conversation_id``
    resumes an existing composite conversation (slice 03 adds a kind-consistency
    check: a single-type conversation id is rejected with 404).
    """

    agent_ids: list[str] = Field(..., min_length=1, max_length=8)
    message: str = Field(..., min_length=1)
    conversation_id: str | None = None
    customer_id: str | None = None
    synthesize_model: str | None = None


class CompositeFragment(BaseModel):
    """One agent's result inside a composite response / assistant Message.

    The token triple (input/output/total) is the slice-03 billing contract:
    each fragment drives one UsageEvent row, so without it the prompt /
    completion columns would be all-zero for composite turns. ``model`` is the
    model that actually served this agent (resolved tenant > platform > env),
    capped at 64 chars to mirror Agent.model / Message.model.
    """

    agent_id: str
    agent_name: str
    snippet: str
    status: Literal["completed", "failed"]
    error: str | None = None
    model: str | None = Field(None, max_length=64)
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class CompositeResponse(BaseModel):
    """Response of POST /chat/composite — the synthesis plus the per-agent fragments.

    ``fragments`` is the same list persisted on the assistant Message.fragments
    JSONB, so the client history view (GET /conversations/{id}/messages) shows
    identical data to the live response.
    """

    conversation_id: str
    synthesis: str
    fragments: list[CompositeFragment]
