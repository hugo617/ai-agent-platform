"""Minimal LangGraph agent with one tool.

The tool ``get_my_agents`` lets the LLM list the agents owned by the current
tenant — proving that the agent's tool calls are themselves subject to the
multi-tenant permission model (no cross-tenant data leakage).
"""

from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessageChunk, BaseMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.repositories.agent import AgentRepository
from app.services.permission_service import permission_service


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


def build_agent(system_prompt: str = "") -> Any:
    """Build the LangGraph ReAct agent with the configured chat model."""
    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        streaming=True,
        temperature=0.3,
    )
    prompt = system_prompt or (
        "You are a helpful assistant for a multi-tenant SaaS platform. "
        "You can list the agents available in the current tenant by calling "
        "the `get_my_agents` tool. Always be concise."
    )
    # NOTE: tools are injected per-request; this returns an empty-tool agent
    # used as a fallback. The chat endpoint rebinds tools at call time.
    return create_react_agent(llm, tools=[], prompt=prompt)


async def stream_agent(
    *,
    user_id: str,
    tenant_id: str,
    db: AsyncSession,
    system_prompt: str,
    history: list[BaseMessage],
    user_message: str,
) -> AsyncIterator[str]:
    """Run the agent and yield text chunks for SSE streaming.

    Tool calls are awaited; only ``AIMessageChunk`` text content is forwarded
    to the client.
    """
    from langchain_core.messages import HumanMessage

    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        streaming=True,
        temperature=0.3,
    )
    tools = _build_tenant_tools(user_id, tenant_id, db)
    prompt = system_prompt or (
        "You are a helpful assistant. Use `get_my_agents` to list the agents in "
        "the current tenant when asked."
    )
    agent = create_react_agent(llm, tools=tools, prompt=prompt)

    inputs = [*history, HumanMessage(content=user_message)]
    async for event in agent.astream_events(inputs, version="v2"):
        kind = event["event"]
        if kind == "on_chat_model_stream":
            chunk = event["data"].get("chunk")
            if isinstance(chunk, AIMessageChunk) and chunk.content:
                yield chunk.content
