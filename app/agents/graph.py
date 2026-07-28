"""Minimal LangGraph agent with tools.

Two tools are bound per (user, tenant) context:

- ``get_my_agents`` — list the agents owned by the current tenant, proving that
  tool calls are subject to the multi-tenant permission model.
- ``retrieve_knowledge`` (RAG, priority 57) — search the tenant's knowledge base
  for relevant context and return it so the agent can ground its answer in the
  tenant's own documents (manuals, FAQs, scripts).

Each tool performs its own permission check before touching data, so the agent
cannot bypass authorization regardless of what the LLM emits.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import (
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.agent import Agent
from app.repositories.agent import AgentRepository
from app.services.permission_service import permission_service

logger = logging.getLogger(__name__)

# Wall-clock cap on a single LLM streaming call. Prevents the SSE endpoint
# from hanging indefinitely when the upstream provider stalls (e.g. it rejects
# an over-long prompt but never closes the connection). The timeout covers the
# whole ``astream_events`` loop, so a stuck provider surfaces as
# ``TimeoutError`` to the caller rather than an infinite spinner.
LLM_STREAM_TIMEOUT_SECONDS = 60


def _system_msg(system_prompt: str) -> SystemMessage:
    """Build the system message, defaulting to a concise helpful assistant."""
    return SystemMessage(
        content=system_prompt
        or (
            "You are a helpful assistant. Use `get_my_agents` to list the agents "
            "in the current tenant when asked. Always be concise."
        )
    )


def _build_tenant_tools(user_id: str, tenant_id: str, db: AsyncSession) -> list[Any]:
    """Build tools bound to a specific (user, tenant, db) context.

    Each tool performs its own permission check before touching data, so the
    agent cannot bypass authorization regardless of what the LLM emits.
    """

    @tool
    async def get_my_agents() -> str:
        """List all AI agents defined in the current tenant.

        Returns a newline-separated list of agent names. Returns a denial
        message if the caller lacks the 'read' permission on 'agents'.
        """
        allowed = await permission_service.check(user_id, tenant_id, "agents", "read")
        if not allowed:
            return "ERROR: permission denied"
        repo = AgentRepository(db)
        agents = await repo.list_for_tenant(tenant_id)
        if not agents:
            return "no agents found"
        return "\n".join(f"- {a.name} (model={a.model})" for a in agents)

    @tool
    async def retrieve_knowledge(query: str) -> str:
        """Search the tenant knowledge base for information relevant to a query.

        Call this when the user asks about business-specific content the
        assistant would not otherwise know — product manuals, FAQs, service
        scripts, store policies. Returns the most relevant passages joined by
        a separator, or a 'not found' notice if nothing matches. Only searches
        the current tenant's documents (cross-tenant isolation enforced in the
        repository layer).
        """
        allowed = await permission_service.check(
            user_id, tenant_id, "knowledge", "read"
        )
        if not allowed:
            return "ERROR: permission denied"
        # Imported here to avoid a circular import at module load time
        # (knowledge_service imports embedding_config_service which imports
        # repositories; graph is imported early by the chat route).
        from app.services.knowledge_service import KnowledgeService

        try:
            hits = await KnowledgeService(db).retrieve(query, tenant_id, top_k=4)
        except Exception:
            # Embedding/vector failures must never break the conversation —
            # surface a benign "not found" so the agent keeps chatting.
            return "未找到相关知识"
        if not hits:
            return "未找到相关知识"
        return "\n---\n".join(content for content, _score, _doc_id in hits)

    return [get_my_agents, retrieve_knowledge]


def _build_llm_kwargs(
    *,
    api_key: str,
    base_url: str,
    model: str,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    top_p: float | None = None,
) -> dict[str, Any]:
    """Build kwargs for ``ChatOpenAI`` from resolved inference parameters.

    ``temperature`` is always forwarded (it has a default). ``max_tokens`` and
    ``top_p`` are only included when explicitly set (not None) so an unset
    value means "use the provider default" rather than overriding it.
    """
    kwargs: dict[str, Any] = {
        "model": model,
        "api_key": api_key,
        "base_url": base_url,
        "streaming": True,
        # Ask the provider to aggregate usage in streaming mode. OpenAI-
        # compatible APIs (incl. DeepSeek) only return usage in the *final*
        # SSE chunk, and only when this flag is set — without it the real
        # token counts are silently dropped and we can't bill/report usage.
        "stream_usage": True,
        "temperature": temperature,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if top_p is not None:
        kwargs["top_p"] = top_p
    # Thinking-mode toggle (provider protocol, not a per-agent business param).
    # DeepSeek's OpenAI-compatible API exposes it via extra_body since the SDK
    # doesn't recognise a top-level ``thinking`` field. Only injected when the
    # operator opts OUT of thinking (provider default is thinking-on); models
    # without a thinking mode ignore the param.
    # Local import avoids a config ↔ graph import cycle.
    from app.core.config import settings

    if not settings.llm_thinking_enabled:
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    return kwargs


async def _consume_agent_events(
    agent: Any, inputs: dict
) -> tuple[list[str], dict[str, int]]:
    """Drive one ReAct agent's ``astream_events(version="v2")`` loop to completion.

    Returns ``(text_chunks, usage_acc)`` for the composite fan-out path:
    chunks are joined into a fragment snippet, usage_acc carries the summed
    tokens across every ``on_chat_model_end`` (a ReAct turn may call the LLM
    several times; ``ainvoke`` would only report the last round and silently
    under-count).

    NOT shared with ``stream_agent``: that path yields each chunk to the SSE
    client *as it arrives* (typewriter effect), so it cannot batch-collect.
    The accumulation shape looks duplicated but the semantics diverge —
    extracting a shared helper would force ``stream_agent`` to buffer the
    whole reply before sending the first byte, breaking its streaming contract.
    """
    chunks: list[str] = []
    usage_acc = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    async for event in agent.astream_events(inputs, version="v2"):
        kind = event["event"]
        if kind == "on_chat_model_stream":
            chunk = event["data"].get("chunk")
            if isinstance(chunk, AIMessageChunk) and chunk.content:
                chunks.append(chunk.content)
        elif kind == "on_chat_model_end":
            output = event["data"].get("output")
            um = getattr(output, "usage_metadata", None)
            if um:
                usage_acc["input_tokens"] += um.get("input_tokens", 0)
                usage_acc["output_tokens"] += um.get("output_tokens", 0)
                usage_acc["total_tokens"] += um.get("total_tokens", 0)
    return chunks, usage_acc


def build_agent(
    *,
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str = "",
    temperature: float = 0.7,
    max_tokens: int | None = None,
    top_p: float | None = None,
) -> Any:
    """Build the LangGraph ReAct agent with the given chat model.

    The caller resolves the LLM credentials/model (tenant > platform > env) and
    passes them in — this function never touches global settings, so which
    model actually serves a chat is decided by the caller, not by config.
    """
    llm = ChatOpenAI(**_build_llm_kwargs(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
    ))
    # langgraph 0.2.x takes the system prompt via ``messages_modifier`` (a
    # SystemMessage prepended to the state); the ``prompt`` kwarg arrived in a
    # later version.
    return create_react_agent(llm, tools=[], messages_modifier=_system_msg(system_prompt))


async def stream_agent(
    *,
    user_id: str,
    tenant_id: str,
    db: AsyncSession,
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str,
    history: list[BaseMessage],
    user_message: str,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    top_p: float | None = None,
) -> AsyncIterator[str | dict[str, Any]]:
    """Run the agent and yield text chunks for SSE streaming, then usage.

    Yields ``str`` text chunks while streaming (forwarded to the client as
    SSE ``delta`` frames). After the stream ends, yields a single ``dict``
    with the aggregated token usage and the model that actually served the
    request — callers persist this so the platform knows how many tokens a
    chat consumed (the foundation of billing/quotas).

    The usage dict shape: ``{"usage": {...}, "model": str}`` where usage has
    ``input_tokens``/``output_tokens``/``total_tokens``. Usage is accumulated
    across every ``on_chat_model_end`` event: a ReAct agent may invoke the
    LLM more than once per turn (think → tool → think again), so we sum
    every call's ``usage_metadata`` rather than taking the last one.

    Tool calls are awaited; only ``AIMessageChunk`` text content is forwarded
    to the client. The LLM (key/base_url/model) is resolved by the caller and
    passed in — this is what makes ``Agent.model`` actually take effect.
    Inference parameters (temperature/max_tokens/top_p) come from the Agent
    config; ``max_tokens``/``top_p`` of None mean "use provider default".
    """
    llm = ChatOpenAI(**_build_llm_kwargs(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
    ))
    tools = _build_tenant_tools(user_id, tenant_id, db)
    agent = create_react_agent(
        llm, tools=tools, messages_modifier=_system_msg(system_prompt)
    )

    # ReAct agent expects a state dict (``{"messages": [...]}``), not a bare
    # list — passing the list directly raises INVALID_GRAPH_NODE_RETURN_VALUE.
    inputs = {"messages": [*history, HumanMessage(content=user_message)]}
    # Accumulate token usage across every LLM call in this turn. A ReAct
    # agent can call the model several times (reasoning → tool → reasoning),
    # and each ``on_chat_model_end`` carries that call's ``usage_metadata`` —
    # we sum them so the recorded total reflects the real cost of the turn.
    usage_acc = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    # Guard the whole stream against a stalled upstream: if the provider
    # hangs (network black-hole, over-long prompt rejected silently, etc.)
    # ``asyncio.timeout`` cancels the generator and raises ``TimeoutError``,
    # which the chat endpoint surfaces as an error frame instead of spinning
    # forever. Python 3.11+ provides ``asyncio.timeout`` as a context manager.
    async with asyncio.timeout(LLM_STREAM_TIMEOUT_SECONDS):
        async for event in agent.astream_events(inputs, version="v2"):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if isinstance(chunk, AIMessageChunk) and chunk.content:
                    yield chunk.content
            elif kind == "on_chat_model_end":
                output = event["data"].get("output")
                um = getattr(output, "usage_metadata", None)
                if um:
                    usage_acc["input_tokens"] += um.get("input_tokens", 0)
                    usage_acc["output_tokens"] += um.get("output_tokens", 0)
                    usage_acc["total_tokens"] += um.get("total_tokens", 0)
    # Hand the aggregated usage + serving model to the caller so it can be
    # persisted on the assistant Message and in the UsageEvent ledger. Yielded
    # last, after all text chunks — callers distinguish via isinstance.
    yield {"usage": usage_acc, "model": model}


# --------------------------------------------------------------- composite-chat (72)
#
# Composite query: fan-out the SAME user question to N agents in parallel,
# then synthesize their answers into one reply. This is the "ask everyone,
# merge" counterpart to the Supervisor's "route to the right one" — both
# coexist (Supervisor = find the expert; Composite = merge many viewpoints).
#
# Why a separate path (not reusing ``stream_agent``):
#   1. ``stream_agent`` is an SSE ``yield`` contract; N parallel streams
#      interleaved on one socket would garble the client. ``composite_query``
#      returns a single dict — no streaming to the caller.
#   2. ReAct agents may call the LLM several times per turn (think → tool →
#      think). ``ainvoke`` returns only the LAST round's ``usage_metadata``
#      and silently under-counts multi-round token cost; ``_invoke_agent_once``
#      uses ``astream_events(version="v2")`` to sum every ``on_chat_model_end``
#      (same mechanism ``stream_agent`` relies on for accurate billing).
#
# Concurrency safety (plan §Step 5, decision A): SQLAlchemy ``AsyncSession``
# is NOT concurrent-safe. If N agents shared the request's session and more
# than one called the ``retrieve_knowledge`` tool simultaneously, the session
# would raise. So each agent gets its OWN session from the factory, and the
# ``_build_tenant_tools`` closure is rebuilt per agent against that session.
# The main request session (``db``) is only used for the single synthesize
# call, which has no concurrency.

# Per-agent wall-clock cap for the fan-out. Generous on purpose — a ReAct
# turn with tool calls can legitimately take 20s+ on a slow provider; we
# don't want to abandon a working agent. The default scales with agent
# count so a larger fan-out isn't squeezed by the same budget as a small one.
def _default_fanout_timeout(agent_count: int) -> float:
    return agent_count * 30 + 60


def _fallback_synthesis(fragments: list[dict]) -> str:
    """Render a best-effort synthesis when the synthesize LLM call fails.

    Pure function (no I/O) so it is trivially unit-testable. Each completed
    fragment becomes a section under its agent's name; each failed fragment
    becomes a bracketed failure notice. Sections are joined by a horizontal
    rule so the result is still readable markdown.
    """
    parts: list[str] = []
    for f in fragments:
        if f["status"] == "completed":
            parts.append(f"## {f['agent_name']}\n{f['snippet']}")
        else:
            parts.append(
                f"## {f['agent_name']}\n[此 agent 失败: {f['error']}]"
            )
    return "\n\n---\n\n".join(parts)


def _synthesize_prompt(message: str, fragments: list[dict]) -> str:
    """Build the prompt handed to the synthesize LLM (pure function).

    Failed fragments contribute a bracketed notice so the synthesizer knows
    that agent didn't answer (and can say so in the merged reply rather than
    silently dropping it).
    """
    lines = [
        "你是综合编辑。下面是多个 AI 助手对同一问题的独立回答。",
        "请综合它们的观点,给出一份完整、不重复、保留各方要点的回答。",
        "如果某助手失败,简要说明其未能贡献,不要伪造其内容。",
        "",
        f"用户问题:{message}",
        "",
        "各助手回答:",
    ]
    for f in fragments:
        if f["status"] == "completed":
            lines.append(f"### {f['agent_name']}\n{f['snippet']}")
        else:
            lines.append(
                f"### {f['agent_name']}\n[此 agent 失败: {f['error']}]"
            )
    return "\n\n".join(lines)


# Composite cost-control default: cap each agent's reply when the agent itself
# hasn't set ``max_tokens``. N+1 LLM calls is expensive; an unbounded reply
# per agent would balloon cost. Agents that explicitly set ``max_tokens``
# keep their value (300 is a fallback, not a clamp).
_COMPOSITE_DEFAULT_MAX_TOKENS = 300

# Synthesize is one summary call; allow it more room than a single fragment
# but still bounded — it's merging N answers, not generating fresh content.
_SYNTHESIZE_MAX_TOKENS = 600


async def _invoke_agent_once(
    *,
    agent: Agent,
    user_id: str,
    tenant_id: str,
    api_key: str,
    base_url: str,
    message: str,
) -> dict:
    """Run ONE agent against the question and return its fragment dict.

    Builds the agent's own ``ChatOpenAI`` (honoring its model / temperature /
    max_tokens) + a fresh ``create_react_agent`` with tenant tools bound to a
    **dedicated session** (concurrency-safe). Drives the agent via
    ``astream_events(version="v2")`` so every ``on_chat_model_end`` usage is
    summed — a ReAct turn may call the model several times and ``ainvoke``
    would only report the last round. Returns synchronously (a dict), never
    a stream — the caller fans out many of these in parallel via ``gather``.

    The ``db`` (session) is opened here, not passed in: each agent MUST own
    its session to stay concurrent-safe (plan decision A). The session is
    used only by this agent's tool closures and is closed when the block
    exits — agent reads commit independently of the main request session.

    Returns ``{agent_id, agent_name, snippet, status, error, model,
    input_tokens, output_tokens, total_tokens}``. ``status`` is ``"completed"``
    on success or ``"failed"`` (with ``error`` set) if anything raised — the
    fragment is always returned so the outer fan-out can record it.
    """
    # max_tokens: explicit agent config wins; otherwise the composite default
    # caps reply length for cost control (N+1 calls is expensive).
    max_tokens = agent.max_tokens
    if max_tokens is None:
        max_tokens = _COMPOSITE_DEFAULT_MAX_TOKENS

    fragment: dict[str, Any] = {
        "agent_id": agent.id,
        "agent_name": agent.name,
        "snippet": "",
        "status": "failed",  # flipped to completed only on full success
        "error": None,
        "model": agent.model,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }

    try:
        llm = ChatOpenAI(**_build_llm_kwargs(
            api_key=api_key,
            base_url=base_url,
            model=agent.model,
            temperature=agent.temperature,
            max_tokens=max_tokens,
            top_p=agent.top_p,
        ))
        # Each agent gets its OWN session — AsyncSession is not concurrent-
        # safe and N parallel ReAct turns sharing one session would corrupt.
        # ``_build_tenant_tools`` closes over this session so the agent's
        # RAG tool reads through it; commits are independent per agent.
        async with AsyncSessionLocal() as session:
            tools = _build_tenant_tools(user_id, tenant_id, session)
            react = create_react_agent(
                llm, tools=tools, messages_modifier=_system_msg(agent.system_prompt)
            )
            inputs = {"messages": [HumanMessage(content=message)]}
            # Drive the stream to completion, summing usage across every LLM
            # call in this turn (ReAct may invoke the model several times).
            snippet_parts, usage_acc = await _consume_agent_events(react, inputs)

        fragment.update({
            "snippet": "".join(snippet_parts),
            "status": "completed",
            "error": None,
            "input_tokens": usage_acc["input_tokens"],
            "output_tokens": usage_acc["output_tokens"],
            "total_tokens": usage_acc["total_tokens"],
        })
    except Exception as exc:  # noqa: BLE001 - isolate per-agent failures
        # One agent's failure must NEVER take down the others. Record the
        # error in the fragment and return it; the fan-out's per-agent
        # try/except guarantees ``gather`` never sees an exception. Logged
        # at error level (not silently swallowed) so a systemic provider
        # outage surfaces in ops — a single agent flapping is expected, but
        # ALL agents failing the same way is a signal worth investigating.
        logger.exception(
            "composite agent %s (%s) failed; isolated to fragment",
            agent.id, agent.name,
        )
        fragment["error"] = str(exc)
    return fragment


async def composite_query(
    *,
    user_id: str,
    tenant_id: str,
    db: AsyncSession,
    api_key: str,
    base_url: str,
    agents: list[Agent],
    message: str,
    synthesize_model: str | None = None,
    fanout_timeout: float | None = None,
) -> dict:
    """Fan-out a question to N agents, then synthesize their answers.

    Pipeline:
      Pass 2 (fan-out) — every agent runs ``_invoke_agent_once`` in parallel
        via ``asyncio.gather``, wrapped in ``asyncio.wait_for``. Each task
        appends its fragment to an OUTER list (not just returns it) so that
        if the timeout fires, already-completed fragments survive even
        though ``gather``'s return value is lost.
      Pass 3 (synthesize) — one LLM call merges the fragments into a single
        synthesis. Failures degrade to ``_fallback_synthesis`` (the raw
        fragments concatenated) so the user always gets a reply.

    Returns ``{synthesis, fragments, synthesize_usage, usage_total}``:
      - ``synthesis`` — the merged answer (or fallback concatenation)
      - ``fragments`` — per-agent rows (status completed/failed, tokens, ...)
      - ``synthesize_usage`` — the synthesize call's token usage (zeroed on
        degradation); carries ``model`` so the caller can bill the N+1th row
      - ``usage_total`` — Σ(fragments.tokens) + synthesize_usage.tokens, the
        aggregate persisted on the assistant Message

    ``synthesize_model`` overrides which model serves the merge (defaults to
    ``agents[0].model``). ``fanout_timeout`` overrides the wall-clock cap on
    the parallel fan-out (defaults to ``N*30+60`` seconds); kept as a param
    so tests can shrink it — production callers should let the default run.
    """
    n = len(agents)
    timeout = fanout_timeout if fanout_timeout is not None else _default_fanout_timeout(n)

    # Outer container: tasks append here. On timeout the gather's return
    # value is unreachable, but this list retains whatever completed first.
    fragments: list[dict] = []

    async def _run_one(agent: Agent) -> None:
        # Per-agent try/except converts any exception into a failed fragment
        # appended to ``fragments``. ``gather`` therefore never sees a raised
        # exception and doesn't need ``return_exceptions=True`` — we want a
        # structured fragment dict (with agent_name/error), not a raw Exception.
        try:
            frag = await _invoke_agent_once(
                agent=agent, user_id=user_id, tenant_id=tenant_id,
                api_key=api_key, base_url=base_url, message=message,
            )
            fragments.append(frag)
        except Exception as exc:  # noqa: BLE001 - last-resort isolation
            # ``_invoke_agent_once`` already converts most failures into a
            # failed fragment; this outer guard catches anything that escapes
            # (e.g. session factory failure before the agent runs). Logged so
            # the rare uncaught path isn't invisible.
            logger.exception(
                "composite _run_one outer guard caught for agent %s", agent.id,
            )
            fragments.append({
                "agent_id": agent.id, "agent_name": agent.name,
                "snippet": "", "status": "failed", "error": str(exc),
                "model": agent.model,
                "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
            })

    # Fan-out. NOT ``async with asyncio.timeout(...)`` — that would cancel
    # every task on timeout and we'd lose even the completed fragments.
    # ``wait_for`` raises ``TimeoutError`` but the outer list already holds
    # whatever finished; we swallow the timeout and proceed to synthesize
    # on whatever fragments we have (fail-open).
    try:
        await asyncio.wait_for(
            asyncio.gather(*[_run_one(a) for a in agents]),
            timeout=timeout,
        )
    except TimeoutError:
        # Abandoned tasks' fragments never made it into ``fragments``; the
        # ones that did complete are kept and synthesized below. This is
        # the fail-open contract: a slow agent doesn't poison the whole reply.
        # Logged as a warning (not silent) — a timeout means at least one
        # agent didn't answer, which the caller should be able to correlate
        # in logs even though the response still succeeds.
        logger.warning(
            "composite fan-out timed out after %.1fs; %d/%d agents completed",
            timeout, len(fragments), n,
        )

    # Pass 3: synthesize. The model is the explicit override, else the first
    # agent's model (a stable, tenant-configured choice — never env fallback).
    synth_model = synthesize_model or agents[0].model
    synthesis: str
    synth_input = synth_output = synth_total = 0
    try:
        synth_llm = ChatOpenAI(**_build_llm_kwargs(
            api_key=api_key, base_url=base_url, model=synth_model,
            # Synthesize is a deterministic merge, not creative generation —
            # lower temperature than the fan-out agents (which use their own
            # configured value) so the merged answer sticks closely to what
            # the agents actually said rather than drifting. Plan §Step 5
            # pins max_tokens=600 but not temperature; 0.3 mirrors StorePilot's
            # synthesis step (the design lineage documented in the plan).
            temperature=0.3, max_tokens=_SYNTHESIZE_MAX_TOKENS,
        ))
        # Single LLM call, no tools — synthesize is a pure text merge.
        # ``ainvoke`` is safe here (one round, no multi-round undercount).
        result = await synth_llm.ainvoke(
            _synthesize_prompt(message, fragments)
        )
        synthesis = result.content if hasattr(result, "content") else str(result)
        um = getattr(result, "usage_metadata", None)
        if um:
            synth_input = um.get("input_tokens", 0)
            synth_output = um.get("output_tokens", 0)
            synth_total = um.get("total_tokens", 0)
    except Exception:  # noqa: BLE001 - synthesize must not fail the request
        # Degrade: concatenate the raw fragments so the user still sees every
        # agent's answer. usage is zeroed (no tokens consumed by a failed call
        # we can observe); model is kept so the N+1th ledger row is consistent.
        # Logged at error level — synthesize failing is rare and worth ops
        # attention (all agents answered but the merge step broke).
        logger.exception(
            "composite synthesize failed (model=%s); degrading to fallback",
            synth_model,
        )
        synthesis = _fallback_synthesis(fragments)

    synthesize_usage = {
        "input_tokens": synth_input,
        "output_tokens": synth_output,
        "total_tokens": synth_total,
        "model": synth_model,
    }

    # Aggregate every fragment's tokens + the synthesize call's tokens.
    total_in = sum(f["input_tokens"] for f in fragments) + synth_input
    total_out = sum(f["output_tokens"] for f in fragments) + synth_output
    total_all = sum(f["total_tokens"] for f in fragments) + synth_total
    usage_total = {
        "input_tokens": total_in,
        "output_tokens": total_out,
        "total_tokens": total_all,
    }

    return {
        "synthesis": synthesis,
        "fragments": fragments,
        "synthesize_usage": synthesize_usage,
        "usage_total": usage_total,
    }


# --------------------------------------------------------------- multi-agent (58)
#
# Supervisor orchestration: an orchestrator Agent doesn't answer itself — it
# asks a routing LLM "which specialist should handle this?" then hands the
# whole message history to that specialist's own ReAct agent. We build this
# as a LangGraph ``StateGraph`` so the specialist's ``create_react_agent`` is
# a real node and its ``on_chat_model_stream`` events bubble up through the
# outer graph's ``astream_events`` (the same v2 contract ``stream_agent``
# relies on), preserving both the typewriter SSE effect and per-call usage
# accounting.
from langgraph.graph import END, START, MessagesState, StateGraph  # noqa: E402
from langgraph.types import Command  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402


class _RouteDecision(BaseModel):
    """Structured output the supervisor LLM must return.

    ``specialist_id`` is the Agent.id of the chosen specialist. The supervisor
    is told the candidate ids in its prompt, so a well-behaved model returns
    one of them; anything else falls back to the first specialist.
    """

    specialist_id: str = Field(description="选中的 specialist Agent id")
    reason: str = Field(default="", description="一句话路由理由(中文)")


def _build_supervisor_prompt(specialists: list[Any]) -> str:
    """Render the routing prompt listing each specialist's id/name/specialty.

    ``specialists`` are Agent ORM rows. Kept as a pure function so it is
    trivially unit-testable without an LLM.
    """
    lines = [
        "你是智能体路由编排器。根据用户问题,选择最合适的 specialist 来回答。",
        "只能从下方候选中选择,返回其 specialist_id。",
        "候选 specialist:",
    ]
    for sp in specialists:
        role = sp.specialty or sp.description or "通用助手"
        lines.append(f"- specialist_id={sp.id} | 名称={sp.name} | 职责={role}")
    lines.append("如果问题与任何 specialist 的职责都不匹配,选择最接近的一个,不要拒绝。")
    return "\n".join(lines)


def _resolve_route_target(
    decision: Any, specialists: list[Any]
) -> str:
    """Map the supervisor's decision to a real specialist id, with fallback.

    Pure function: returns the decision's specialist_id if it matches one of
    the candidates, otherwise the first specialist's id (never raises — the
    caller already guaranteed ``specialists`` is non-empty).
    """
    candidate_ids = {sp.id for sp in specialists}
    chosen = getattr(decision, "specialist_id", None)
    if chosen and chosen in candidate_ids:
        return chosen
    return specialists[0].id


def build_orchestrator(
    *,
    supervisor_llm: ChatOpenAI,
    specialists: list[Any],
    specialist_factories: dict[str, Any],
    user_id: str,
    tenant_id: str,
    db: AsyncSession,
) -> Any:
    """Compile the supervisor multi-agent graph.

    Layout (MVP, single-pass — no supervisor loop):

        START → supervisor → specialist_X → END

    The supervisor node asks the routing LLM which specialist should handle
    the latest user message, then returns ``Command(goto=<specialist_id>)``.
    Each specialist is a full ``create_react_agent`` (it keeps its own tools,
    e.g. ``retrieve_knowledge``), wired as its own graph node so its
    ``on_chat_model_stream`` events propagate to the outer ``astream_events``.

    ``specialists`` — the Agent ORM rows (for routing prompt + id matching).
    ``specialist_factories`` — ``{agent_id: compiled_react_agent}``; the caller
    builds each specialist's ReAct agent once (with its own tools/prompt) and
    passes the compiled graph here so the orchestrator doesn't rebuild per
    turn.
    """
    graph = StateGraph(MessagesState)
    structured_router = supervisor_llm.with_structured_output(_RouteDecision)
    supervisor_prompt = _build_supervisor_prompt(specialists)
    fallback_id = specialists[0].id

    async def supervisor_node(state: dict[str, Any]) -> Command:
        # Ask the routing LLM which specialist fits the latest user message.
        # ``state["messages"]`` always includes the just-added HumanMessage
        # (the outer caller assembled history + user_message before invoking).
        try:
            decision = await structured_router.ainvoke(
                [SystemMessage(content=supervisor_prompt), *state["messages"]]
            )
            target = _resolve_route_target(decision, specialists)
        except Exception:  # noqa: BLE001 - routing must never break the chat
            # Any router failure (API error, malformed JSON, parse error) falls
            # back to the first specialist so the user still gets an answer.
            target = fallback_id
        # Route to the chosen specialist without injecting a new message — the
        # specialist sees the full conversation history as-is.
        return Command(goto=target)

    graph.add_node("supervisor", supervisor_node)
    for sp in specialists:
        react_agent = specialist_factories[sp.id]
        graph.add_node(sp.id, react_agent)
    graph.add_edge(START, "supervisor")
    # MVP: each specialist answers once and the turn ends. We deliberately do
    # NOT route back to supervisor after a specialist answers — that would
    # multiply LLM calls (latency + tokens) for marginal routing gain, and
    # risks loops. Multi-step handoff is a V2 concern (see plan §不做的事).
    for sp in specialists:
        graph.add_edge(sp.id, END)
    return graph.compile()


async def stream_orchestrator(
    *,
    user_id: str,
    tenant_id: str,
    db: AsyncSession,
    api_key: str,
    base_url: str,
    model: str,
    orchestrator: Any,
    specialists: list[Any],
    history: list[BaseMessage],
    user_message: str,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    top_p: float | None = None,
) -> AsyncIterator[str | dict[str, Any]]:
    """Run the orchestrator graph and yield text chunks + usage (SSE contract).

    Same yield contract as ``stream_agent``: ``str`` text chunks while the
    chosen specialist streams its reply, then a final
    ``{"usage": {...}, "model": str}`` dict. The supervisor's own routing LLM
    call is also accounted in ``usage`` (its ``on_chat_model_end`` event fires
    inside the same ``astream_events`` loop).
    """
    # Supervisor uses a low temperature for stable, deterministic routing.
    supervisor_llm = ChatOpenAI(
        **_build_llm_kwargs(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=0.1,
            max_tokens=max_tokens,
            top_p=top_p,
        )
    )
    tools = _build_tenant_tools(user_id, tenant_id, db)
    # Build each specialist's ReAct agent once. Specialists inherit the
    # orchestrator's resolved LLM credentials (tenant config) but keep their
    # own system_prompt and the shared tenant tools (retrieve_knowledge etc.).
    specialist_factories: dict[str, Any] = {}
    for sp in specialists:
        sp_llm = ChatOpenAI(
            **_build_llm_kwargs(
                api_key=api_key,
                base_url=base_url,
                model=model,
                temperature=sp.temperature if sp.temperature is not None else temperature,
                max_tokens=sp.max_tokens,
                top_p=sp.top_p,
            )
        )
        specialist_factories[sp.id] = create_react_agent(
            sp_llm, tools=tools, messages_modifier=_system_msg(sp.system_prompt)
        )

    graph = build_orchestrator(
        supervisor_llm=supervisor_llm,
        specialists=specialists,
        specialist_factories=specialist_factories,
        user_id=user_id,
        tenant_id=tenant_id,
        db=db,
    )

    inputs = {"messages": [*history, HumanMessage(content=user_message)]}
    usage_acc = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    async with asyncio.timeout(LLM_STREAM_TIMEOUT_SECONDS):
        async for event in graph.astream_events(inputs, version="v2"):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if isinstance(chunk, AIMessageChunk) and chunk.content:
                    yield chunk.content
            elif kind == "on_chat_model_end":
                output = event["data"].get("output")
                um = getattr(output, "usage_metadata", None)
                if um:
                    usage_acc["input_tokens"] += um.get("input_tokens", 0)
                    usage_acc["output_tokens"] += um.get("output_tokens", 0)
                    usage_acc["total_tokens"] += um.get("total_tokens", 0)
    yield {"usage": usage_acc, "model": model}
