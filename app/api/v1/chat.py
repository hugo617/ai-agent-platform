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
from app.models.agent import Agent, Conversation
from app.models.message import Message
from app.models.usage_event import UsageEvent
from app.repositories.agent import AgentRepository
from app.repositories.conversation import MessageRepository
from app.repositories.usage_event import UsageEventRepository
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


def _u(usage_data: dict | None, key: str) -> int | None:
    """Read a token count from the usage payload, None-safe.

    Returns None when there's no usage (e.g. a stubbed stream in tests or a
    provider that didn't return usage) so the Message column stays NULL.
    """
    if usage_data is None:
        return None
    val = usage_data.get("usage", {}).get(key)
    return int(val) if val is not None else None


async def _record_usage(
    db: AsyncSession,
    conv: Conversation,
    msg: Message,
    agent: Agent,
    user: CurrentUser,
    usage_data: dict | None,
) -> UsageEvent | None:
    """Append a UsageEvent ledger row for this assistant turn.

    No-op when there's no usage data (stubbed streams / provider didn't
    return usage). Wrapped in try/except so a ledger write failure never
    surfaces to the user — the chat already succeeded, losing one usage
    record is preferable to erroring the whole reply.

    Returns the persisted ``UsageEvent`` (so the caller can pass it to
    ``BillingService.charge``), or None when nothing was recorded.
    """
    if usage_data is None:
        return None
    total = _u(usage_data, "total_tokens")
    if total is None:
        return None
    try:
        repo = UsageEventRepository(db)
        event = await repo.add(
            UsageEvent(
                tenant_id=conv.tenant_id,
                conversation_id=conv.id,
                message_id=msg.id,
                agent_id=agent.id,
                customer_id=None,  # filled by task 3 (customer-conversation-link)
                user_id=user.user_id,
                model=usage_data.get("model") or "",
                prompt_tokens=_u(usage_data, "input_tokens") or 0,
                completion_tokens=_u(usage_data, "output_tokens") or 0,
                total_tokens=total,
                cost=None,  # filled by BillingService.charge below
            )
        )
        await db.commit()
        return event
    except Exception:  # noqa: BLE001 - ledger is best-effort
        # Drop the pending usage_events insert only — the assistant message
        # was already committed by ``append_message``, so it survives the
        # rollback. We swallow the error to keep the chat reply intact.
        await db.rollback()
        return None


async def _charge_usage(
    db: AsyncSession, tenant_id: str, event: UsageEvent | None
) -> None:
    """Debit the wallet for a usage event (best-effort, never blocks).

    Runs after the assistant message + usage event are committed, so a billing
    failure is logged and swallowed — we never break a finished chat over a
    bookkeeping error. Discrepancies are reconciled from the usage_events
    ledger (which is the authoritative record of consumption).
    """
    if event is None:
        return
    try:
        from app.services.billing_service import BillingService

        await BillingService(db).charge(tenant_id, event, operator_id=None)
    except Exception:  # noqa: BLE001 - billing is best-effort
        await db.rollback()


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
        usage_data: dict | None = None
        # Balance pre-check: when a wallet EXISTS and its balance has hit zero,
        # block new chats with an SSE ``error`` event (HTTP 200 is already
        # sent, so switching to an error code mid-stream is not SSE-friendly).
        # A missing wallet is intentionally NOT blocked — it covers tenants
        # created before billing was enabled (and the test environment), so the
        # platform degrades gracefully instead of locking everyone out.
        # super_admin bypasses the gate entirely (platform-level, never billed).
        if user.platform_role != "super_admin":
            try:
                from app.services.billing_service import BillingService

                wallet = await BillingService(db).get_wallet(user.tenant_id)
                if wallet is not None and wallet.balance <= 0:
                    yield f"data: {json.dumps({'error': 'token 余额不足,请联系总部充值'}, ensure_ascii=False)}\n\n"
                    return
            except Exception:  # noqa: BLE001 - billing must never block chat
                # If the billing lookup itself fails, do not punish the user —
                # let the chat proceed. The discrepancy is reconciled later.
                pass
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
            async for item in stream_agent(
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
                # stream_agent yields str chunks during streaming and a
                # single {"usage": {...}, "model": str} dict at the end.
                if isinstance(item, str):
                    full_reply.append(item)
                    yield f"data: {json.dumps({'delta': item}, ensure_ascii=False)}\n\n"
                elif isinstance(item, dict) and "usage" in item:
                    usage_data = item
        except Exception as e:  # noqa: BLE001 - surface to client then close
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            # Fault tolerance: if the stream produced a partial reply before
            # failing, persist what we have (marked interrupted) so the
            # conversation history stays continuous — otherwise the user sees
            # their question with no answer on reload. An empty reply is
            # skipped to avoid storing a blank assistant message. Token usage
            # (if any was captured before the failure) is still recorded.
            partial = "".join(full_reply)
            if partial.strip():
                msg = await conv_service.append_message(
                    conv.tenant_id,
                    conv.id,
                    "assistant",
                    partial + "\n\n[生成中断]",
                    prompt_tokens=_u(usage_data, "input_tokens"),
                    completion_tokens=_u(usage_data, "output_tokens"),
                    total_tokens=_u(usage_data, "total_tokens"),
                    model=usage_data.get("model") if usage_data else None,
                )
                event = await _record_usage(
                    db, conv, msg, agent, user, usage_data
                )
                # Debit the wallet for the consumed tokens (best-effort: a
                # billing error never breaks an otherwise-completed reply).
                await _charge_usage(db, user.tenant_id, event)
            return

        # Persist the assistant reply once streaming completes, carrying the
        # aggregated token usage + serving model so each message is
        # self-describing for billing/reporting.
        msg = await conv_service.append_message(
            conv.tenant_id,
            conv.id,
            "assistant",
            "".join(full_reply),
            prompt_tokens=_u(usage_data, "input_tokens"),
            completion_tokens=_u(usage_data, "output_tokens"),
            total_tokens=_u(usage_data, "total_tokens"),
            model=usage_data.get("model") if usage_data else None,
        )
        # Append a usage ledger entry. Wrapped in try/except so a ledger
        # write failure never breaks an otherwise-successful chat — losing
        # one usage record is preferable to losing the whole reply.
        event = await _record_usage(db, conv, msg, agent, user, usage_data)
        # Debit the wallet for the consumed tokens (best-effort). Runs after
        # the usage event is committed so a billing failure doesn't roll back
        # the message/usage we just persisted.
        await _charge_usage(db, user.tenant_id, event)
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")
