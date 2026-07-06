"""Chat endpoint — SSE streaming of the LangGraph agent's reply.

Permission flow:
  1. The user must have the ``chat`` action on ``conversations`` (casbin).
  2. If a target agent is referenced, it must exist in the same tenant.
  3. Every tool the agent can invoke re-checks permissions at call time.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import stream_agent
from app.api.deps import CurrentUser, get_current_user, require_permission
from app.core.database import get_db
from app.models.agent import Agent
from app.repositories.agent import AgentRepository
from app.repositories.conversation import MessageRepository
from app.schemas.conversation import ChatRequest
from app.services.conversation_service import ConversationService

router = APIRouter(prefix="/chat", tags=["chat"])


async def _load_agent(db: AsyncSession, tenant_id: str, agent_id: str) -> Agent:
    repo = AgentRepository(db)
    agent = await repo.get_for_tenant(agent_id, tenant_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"agent {agent_id} not found in tenant {tenant_id}",
        )
    return agent


@router.post(
    "/stream",
    dependencies=[Depends(require_permission("conversations", "chat"))],
)
async def chat_stream(
    payload: ChatRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream the agent's response as Server-Sent Events."""
    agent = await _load_agent(db, user.tenant_id, payload.agent_id)

    conv_service = ConversationService(db)
    try:
        conv = await conv_service.create_or_get(
            user_id=user.user_id,
            tenant_id=user.tenant_id,
            agent_id=agent.id,
            conversation_id=payload.conversation_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    # Persist the user's message immediately.
    await conv_service.append_message(conv.tenant_id, conv.id, "user", payload.message)

    # Load conversation history as LangChain messages (system prompt is passed
    # separately to ``stream_agent`` so it is NOT duplicated here).
    history_msgs = await MessageRepository(db).list_for_conversation(conv.id, conv.tenant_id)
    history: list[AIMessage | HumanMessage] = []
    for m in history_msgs:
        if m.role == "user":
            history.append(HumanMessage(content=m.content))
        elif m.role == "assistant":
            history.append(AIMessage(content=m.content))

    async def event_source():
        full_reply: list[str] = []
        try:
            async for chunk in stream_agent(
                user_id=user.user_id,
                tenant_id=user.tenant_id,
                db=db,
                system_prompt=agent.system_prompt,
                history=history,
                user_message=payload.message,
            ):
                full_reply.append(chunk)
                yield f"data: {json.dumps({'delta': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001 - surface to client then close
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            return

        # Persist the assistant reply once streaming completes.
        await conv_service.append_message(
            conv.tenant_id, conv.id, "assistant", "".join(full_reply)
        )
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")
