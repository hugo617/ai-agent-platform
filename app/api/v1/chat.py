"""Chat endpoint — SSE streaming of the LangGraph agent's reply.

Permission flow:
  1. The user must have the ``chat`` action on ``conversations`` (casbin).
  2. If a target agent is referenced, it must exist in the same tenant.
  3. Every tool the agent can invoke re-checks permissions at call time.

Composite (priority 72) lives in ``composite_chat`` below — a plain JSON POST
that fans out to N agents and synthesizes one answer (no SSE), billed as N+1
usage events. Contrast with ``chat_stream`` (single agent, SSE, 1 usage event).
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import composite_query, stream_agent
from app.agents.token_budget import truncate_history
from app.api.deps import CurrentUser, get_current_user, require_permission
from app.core.database import get_db
from app.models.agent import Agent, Conversation
from app.models.message import Message
from app.models.usage_event import UsageEvent
from app.repositories.agent import AgentRepository
from app.repositories.conversation import MessageRepository
from app.repositories.usage_event import UsageEventRepository
from app.schemas.conversation import ChatRequest, CompositeRequest, CompositeResponse
from app.services.conversation_service import ConversationService
from app.services.llm_config_service import llm_config_service
from app.services.permission_service import permission_service

logger = logging.getLogger(__name__)

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


async def _require_wallet_balance(db: AsyncSession, user: CurrentUser) -> None:
    """Unified wallet gate shared by BOTH chat paths (chat-stream-wallet-gate).

    super_admin bypasses (platform-level, never billed). Everyone else must
    pass ``BillingService.has_balance`` — wallet exists, active, balance > 0 —
    or get HTTP 402 with the shared detail. Deliberately no try/except: a
    billing lookup failure is a 500 on both paths (fail-open here would reopen
    the free-streaming hole this gate closed).
    """
    if user.platform_role == "super_admin":
        return
    from app.services.billing_service import BillingService

    if not await BillingService(db).has_balance(user.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="token 余额不足,请联系总部充值",
        )


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
                customer_id=conv.customer_id,  # Token 费用管理系列 3/4: 透传
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
        # logger.exception (not a bare pass): composite writes N+1 charge rows
        # per turn, so a silent swallow would multiply a quiet billing bug
        # across every agent + the synthesize step. The SSE path benefits too
        # — a charge failure used to vanish without a trace. (plan §Step 7-8:
        # "except 用 logger.exception,不裸吞".)
        logger.exception(
            "wallet charge failed (tenant=%s, event=%s)", tenant_id, event.id
        )
        await db.rollback()


async def _record_composite_usage(
    db: AsyncSession,
    conv: Conversation,
    msg: Message,
    *,
    agent_id: str | None,
    user: CurrentUser,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    model: str,
) -> UsageEvent | None:
    """Append one UsageEvent ledger row for a composite turn (priority 72).

    NOT shared with ``_record_usage``: that one takes an ``Agent`` object (it
    also pulls tokens out of an SSE usage dict), while composite billing drives
    N+1 rows from already-resolved token triples + a bare ``agent_id`` (None for
    the synthesize row). Each call records one event then charges the wallet
    *paired* (record commit → charge), so a charge failure rolls back only the
    current WalletTransaction, not the committed UsageEvent — see H4.

    best-effort like the SSE path: a ledger/charge failure is logged (NOT
    silently swallowed — N+1 rows amplify the cost of a quiet bug) and the next
    row proceeds, so one bad row never drops the whole batch. Returns the
    persisted event (or None on failure) for test observability.
    """
    try:
        repo = UsageEventRepository(db)
        event = await repo.add(
            UsageEvent(
                tenant_id=conv.tenant_id,
                conversation_id=conv.id,
                message_id=msg.id,
                # None for the synthesize row (the N+1th call has no agent).
                agent_id=agent_id,
                customer_id=conv.customer_id,  #透传:composite 为该 customer 服务
                user_id=user.user_id,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost=None,  # filled by BillingService.charge below
            )
        )
        await db.commit()
    except Exception:  # noqa: BLE001 - ledger is best-effort
        # logger.exception (not a bare pass): composite writes N+1 rows per
        # turn, so a silent swallow would multiply a quiet bug across every
        # agent + the synthesize step. The audit trail matters here.
        logger.exception(
            "composite UsageEvent insert failed (agent_id=%s, conv=%s)",
            agent_id,
            conv.id,
        )
        await db.rollback()
        return None

    # Paired charge: the UsageEvent is committed above, so a charge failure
    # rolls back only the WalletTransaction (best-effort). Reconciliation
    # recovers the gap from the usage_events ledger.
    await _charge_usage(db, conv.tenant_id, event)
    return event


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
    # Wallet gate BEFORE any persistence: a blocked request gets a real 402
    # (not an SSE error frame — those require a 200 already sent) and leaves
    # no conversation/user-message behind. Same function composite calls.
    await _require_wallet_balance(db, user)

    conv_service = ConversationService(db)
    conv = await conv_service.create_or_get(
        user_id=user.user_id,
        tenant_id=user.tenant_id,
        agent_id=agent.id,
        conversation_id=payload.conversation_id,
        platform_role=user.platform_role,
        first_message=payload.message,
        customer_id=payload.customer_id,
    )

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
            # Orchestration (priority 58): an orchestrator Agent routes the
            # message to one of its attached specialists via a supervisor
            # graph instead of answering itself. We look up the specialists
            # here; if the orchestrator has none attached we silently fall
            # back to the plain single-agent path (graceful degradation — the
            # user still gets a reply rather than a dead end).
            stream_kwargs = {
                "user_id": user.user_id,
                "tenant_id": user.tenant_id,
                "db": db,
                "api_key": llm_cfg.api_key,
                "base_url": llm_cfg.base_url,
                "model": model,
                "history": history,
                "user_message": payload.message,
                "temperature": agent.temperature,
                "max_tokens": agent.max_tokens,
                "top_p": agent.top_p,
            }
            if getattr(agent, "is_orchestrator", False):
                from app.agents.graph import stream_orchestrator
                from app.repositories.agent_specialist import (
                    AgentSpecialistRepository,
                )

                specialists = await AgentSpecialistRepository(
                    db
                ).list_specialist_agents(agent.id, user.tenant_id)
                if specialists:
                    stream = stream_orchestrator(
                        orchestrator=agent,
                        specialists=specialists,
                        **stream_kwargs,
                    )
                else:
                    # Empty orchestrator → degrade to plain agent so the chat
                    # still works (the user will just get the orchestrator's
                    # own system_prompt as if it were a normal agent).
                    stream = stream_agent(
                        system_prompt=agent.system_prompt, **stream_kwargs
                    )
            else:
                stream = stream_agent(
                    system_prompt=agent.system_prompt, **stream_kwargs
                )
            async for item in stream:
                # Both stream_agent and stream_orchestrator yield str chunks
                # during streaming and a single {"usage": {...}, "model": str}
                # dict at the end — same contract, so one handler covers both.
                if isinstance(item, str):
                    full_reply.append(item)
                    yield f"data: {json.dumps({'delta': item}, ensure_ascii=False)}\n\n"
                elif isinstance(item, dict) and "usage" in item:
                    usage_data = item
        except Exception as e:  # noqa: BLE001 - surface to client then close
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            # Fault tolerance + auditability: persist the failed turn with
            # status="failed" and the exception text so the failure is
            # auditable and the UI can offer a retry. Any partial reply the
            # stream produced before failing is kept as the content (so the
            # conversation history stays continuous); an empty partial still
            # records a row — a pure provider failure with no content must not
            # vanish silently. Token usage captured before the failure is
            # recorded too.
            partial = "".join(full_reply)
            msg = await conv_service.append_message(
                conv.tenant_id,
                conv.id,
                "assistant",
                partial,
                prompt_tokens=_u(usage_data, "input_tokens"),
                completion_tokens=_u(usage_data, "output_tokens"),
                total_tokens=_u(usage_data, "total_tokens"),
                model=usage_data.get("model") if usage_data else None,
                status="failed",
                error=str(e),
            )
            if usage_data and _u(usage_data, "total_tokens"):
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


# --------------------------------------------------------------- composite (72)
#
# POST /chat/composite — fan out one question to N agents, synthesize one
# answer. Plain JSON (NOT SSE): composite returns a single payload, so there's
# no stream to frame. Contrast with /chat/stream (single agent, typewriter SSE).
# Billed as N+1 UsageEvents (one per agent fragment + one for the synthesize
# call); wallet pre-check via the shared ``_require_wallet_balance`` gate
# (HTTP 402, project-first) — the same function /chat/stream calls.


@router.post(
    "/composite",
    dependencies=[Depends(require_permission("conversations", "chat"))],
    response_model=CompositeResponse,
)
async def composite_chat(
    payload: CompositeRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CompositeResponse:
    """Fan-out one question to N agents in parallel, then synthesize one answer.

    Pipeline (plan §Step 7):
      Pass 1 — resolve + gate. De-duplicate ``agent_ids`` (order-preserving),
        fetch each via ``AgentRepository.get_for_tenant`` (cross-tenant and
        soft-deleted both 404, no existence leak), and re-check
        ``conversations:chat`` per agent. ``agent_ids`` length is already
        bounded 1..8 by the Pydantic schema (422 on violation).
      Wallet pre-check — ``_require_wallet_balance`` (the gate shared with
        /chat/stream): non-super_admin without balance (missing wallet / 0 /
        negative / inactive) → HTTP 402 with the shared detail. Both paths
        calling the same function makes "one wallet contract" structural.
        (Project-first 402; the frontend must catch it separately and show a
        recharge prompt.)
      Create/resume — ``create_or_get(kind="composite")``. New conversation
        stamps ``agent_id=agents[0]`` (the "primary"/attribution anchor); all N
        agents live in fragments. Resuming applies the H2 kind-consistency
        check (single id → 404, blocks single↔composite cross-pollution).
      Pass 2+3 — ``composite_query`` fans out (parallel, per-agent timeout)
        and synthesizes. Failures degrade per-agent (failed fragment) and the
        synthesis falls back to raw concatenation — the request always returns.
      Persist + bill — one assistant Message carries the synthesis + fragments
        (JSONB); N+1 UsageEvents (fragment rows + synthesize row with
        agent_id=None) are recorded and charged pairwise-atomic (H4).
    """
    # ---- Pass 1: resolve + gate --------------------------------------------
    # De-duplicate preserving order (dict.fromkeys): a repeated id must NOT
    # fan out twice (wasted tokens + duplicated fragment + double charge).
    unique_ids = list(dict.fromkeys(payload.agent_ids))
    agent_repo = AgentRepository(db)
    agents: list[Agent] = []
    for aid in unique_ids:
        # get_for_tenant filters tenant_id + is_deleted, so a cross-tenant OR
        # soft-deleted agent both surface as None → 404 (same code, no leak).
        agent = await agent_repo.get_for_tenant(aid, user.tenant_id)
        if agent is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"agent {aid} not found in tenant {user.tenant_id}",
            )
        # Re-check chat permission on this path too (the router-level Depends
        # already gated the user; this mirrors /chat/stream's per-agent intent
        # and keeps a single permission entry point).
        await permission_service.require(
            user.user_id,
            user.tenant_id,
            "conversations",
            "chat",
            platform_role=user.platform_role,
        )
        agents.append(agent)

    # ---- Wallet pre-check --------------------------------------------------
    # Shared gate (was: inline three-liner). super_admin bypasses; everyone
    # else needs a live wallet with balance > 0 — same semantics as
    # /chat/stream, by construction (both call _require_wallet_balance).
    await _require_wallet_balance(db, user)

    # ---- Create / resume composite conversation ---------------------------
    conv_service = ConversationService(db)
    conv = await conv_service.create_or_get(
        user_id=user.user_id,
        tenant_id=user.tenant_id,
        agent_id=agents[0].id,  # primary/attribution anchor (new conv only)
        conversation_id=payload.conversation_id,
        platform_role=user.platform_role,
        first_message=payload.message,
        customer_id=payload.customer_id,
        kind="composite",
    )
    # Persist the user turn immediately (composite_query reads nothing from it,
    # but the history view + future follow-ups need it committed first).
    await conv_service.append_message(conv.tenant_id, conv.id, "user", payload.message)

    # ---- Pass 2+3: fan-out + synthesize ------------------------------------
    llm_cfg = await llm_config_service.get_effective(db, user.tenant_id)
    result = await composite_query(
        user_id=user.user_id,
        tenant_id=user.tenant_id,
        db=db,
        api_key=llm_cfg.api_key,
        base_url=llm_cfg.base_url,
        agents=agents,
        message=payload.message,
        synthesize_model=payload.synthesize_model,
    )

    # ---- Persist the synthesized assistant message (+ fragments) ----------
    # The aggregate usage lands on the Message (self-describing for reporting);
    # the per-agent breakdown lives in fragments (JSONB). model is the
    # synthesize call's model — that's the row a reader attributes this turn to.
    msg = await conv_service.append_message(
        conv.tenant_id,
        conv.id,
        "assistant",
        result["synthesis"],
        prompt_tokens=result["usage_total"]["input_tokens"],
        completion_tokens=result["usage_total"]["output_tokens"],
        total_tokens=result["usage_total"]["total_tokens"],
        model=result["synthesize_usage"]["model"],
        fragments=result["fragments"],
    )

    # ---- N+1 UsageEvents + pairwise charge ---------------------------------
    # Serial (not gather): BillingService.charge takes SELECT...FOR UPDATE,
    # which already serializes — parallel charges would only contend. Each
    # fragment → one event (agent_id set); the synthesize call → one event
    # (agent_id=None). All share message_id = the synthesized Message and
    # customer_id = conv.customer_id (透传).
    for frag in result["fragments"]:
        await _record_composite_usage(
            db,
            conv,
            msg,
            agent_id=frag["agent_id"],
            user=user,
            prompt_tokens=frag["input_tokens"],
            completion_tokens=frag["output_tokens"],
            total_tokens=frag["total_tokens"],
            model=frag["model"],
        )
    # Synthesize row (the N+1th): agent_id=None, model = synth model.
    su = result["synthesize_usage"]
    await _record_composite_usage(
        db,
        conv,
        msg,
        agent_id=None,
        user=user,
        prompt_tokens=su["input_tokens"],
        completion_tokens=su["output_tokens"],
        total_tokens=su["total_tokens"],
        model=su["model"],
    )

    return CompositeResponse(
        conversation_id=conv.id,
        synthesis=result["synthesis"],
        fragments=result["fragments"],
    )
