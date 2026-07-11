"""Minimal LangGraph agent with one tool.

The tool ``get_my_agents`` lets the LLM list the agents owned by the current
tenant — proving that the agent's tool calls are themselves subject to the
multi-tenant permission model (no cross-tenant data leakage).
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

    return [get_my_agents]


def build_agent(
    *,
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str = "",
) -> Any:
    """Build the LangGraph ReAct agent with the given chat model.

    The caller resolves the LLM credentials/model (tenant > platform > env) and
    passes them in — this function never touches global settings, so which
    model actually serves a chat is decided by the caller, not by config.
    """
    llm = ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        streaming=True,
        temperature=0.3,
    )
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
) -> AsyncIterator[str]:
    """Run the agent and yield text chunks for SSE streaming.

    Tool calls are awaited; only ``AIMessageChunk`` text content is forwarded
    to the client. The LLM (key/base_url/model) is resolved by the caller and
    passed in — this is what makes ``Agent.model`` actually take effect.
    """
    from langchain_core.messages import HumanMessage

    llm = ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        streaming=True,
        temperature=0.3,
    )
    tools = _build_tenant_tools(user_id, tenant_id, db)
    agent = create_react_agent(
        llm, tools=tools, messages_modifier=_system_msg(system_prompt)
    )

    # ReAct agent expects a state dict (``{"messages": [...]}``), not a bare
    # list — passing the list directly raises INVALID_GRAPH_NODE_RETURN_VALUE.
    inputs = {"messages": [*history, HumanMessage(content=user_message)]}
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
