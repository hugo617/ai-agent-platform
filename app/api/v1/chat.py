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
from app.agents.token_budget import truncate_history
from app.api.deps import CurrentUser, get_current_user, require_permission
from app.core.database import get_db
from app.models.agent import Agent
from app.repositories.agent import AgentRepository
from app.repositories.conversation import MessageRepository
from app.schemas.conversation import ChatRequest
from app.services.conversation_service import ConversationService
from app.services.errors import NotFoundError
from app.services.llm_config_service import llm_config_service

router = APIRouter(prefix="/chat", tags=["chat"])


def _http_exc(e: ValueError) -> HTTPException:
    """Map a service ValueError to the right HTTP status by exception type."""
    if isinstance(e, NotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


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
            platform_role=user.platform_role,
            first_message=payload.message,
        )
    except ValueError as e:
        raise _http_exc(e) from e

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

    # Sliding-window truncation: keep the conversation within the model's token
    # budget so a long chat doesn't overflow the context window and crash. The
    # oldest messages are dropped first; a minimum floor guarantees recent
    # context always survives. See ``token_budget`` for the heuristic.
    history = truncate_history(history)

    async def event_source():
        full_reply: list[str] = []
        try:
            # Resolve the LLM config (tenant > platform > env) and pick the
            # model: the agent's chosen model wins if it's in the available
            # list, otherwise fall back to the config's default. This is the
            # fix for "Agent.model is ignored" — previously the global config
            # model was always used regardless of agent.model.
            llm_cfg = await llm_config_service.get_effective(db, user.tenant_id)
            model = (
                agent.model
                if agent.model in llm_cfg.available_models
                else llm_cfg.default_model
            )
            async for chunk in stream_agent(
                user_id=user.user_id,
                tenant_id=user.tenant_id,
                db=db,
                api_key=llm_cfg.api_key,
                base_url=llm_cfg.base_url,
                model=model,
                system_prompt=agent.system_prompt,
                history=history,
                user_message=payload.message,
                temperature=agent.temperature,
                max_tokens=agent.max_tokens,
                top_p=agent.top_p,
            ):
                full_reply.append(chunk)
                yield f"data: {json.dumps({'delta': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001 - surface to client then close
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            # Fault tolerance: if the stream produced a partial reply before
            # failing, persist what we have (marked interrupted) so the
            # conversation history stays continuous — otherwise the user sees
            # their question with no answer on reload. An empty reply is
            # skipped to avoid storing a blank assistant message.
            partial = "".join(full_reply)
            if partial.strip():
                await conv_service.append_message(
                    conv.tenant_id,
                    conv.id,
                    "assistant",
                    partial + "\n\n[生成中断]",
                )
            return

        # Persist the assistant reply once streaming completes.
        await conv_service.append_message(
            conv.tenant_id, conv.id, "assistant", "".join(full_reply)
        )
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")
