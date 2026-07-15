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
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessageChunk, BaseMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.agent import AgentRepository
from app.services.permission_service import permission_service

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
    return kwargs


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
    from langchain_core.messages import HumanMessage

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
