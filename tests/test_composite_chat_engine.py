"""Slice 02 — ``composite_query`` orchestration engine unit tests.

Offline (no DeepSeek). We stub ``ChatOpenAI`` + ``create_react_agent`` so the
real ``_invoke_agent_once`` runs its ``astream_events`` accumulation loop
against a fake agent, exactly mirroring ``test_chat.py``'s timeout-test mock
pattern. ``composite_query`` itself is exercised end-to-end with the fake
agents — this validates fan-out, timeout fail-open, synthesize, and usage
accumulation without touching the network.

The HTTP endpoint + billing ledger (slice 03) are out of scope here.
"""

import asyncio

import pytest
from langchain_core.messages import AIMessageChunk

from app.agents.graph import (
    _fallback_synthesis,
    composite_query,
)

# --------------------------------------------------------------- test doubles
#
# Two mock layers, matching how ``composite_query`` uses them:
#
#   1. ``ChatOpenAI(**kwargs)`` → returns a ``_FakeLLM`` carrying the model
#      name (so the fake ``create_react_agent`` can dispatch per-agent) AND
#      a working ``ainvoke()`` (the synthesize path calls the LLM directly,
#      NOT through ``create_react_agent`` — so the mock must support both).
#
#   2. ``create_react_agent(llm, ...)`` → looks up ``llm.model`` in the
#      per-model fake-agent map and returns that scripted ReAct emitter.
#
# A fake ReAct agent's ``astream_events`` emits a scripted sequence of
# ``on_chat_model_stream`` (text chunks) + ``on_chat_model_end`` (per-call
# usage) events, mimicking what LangGraph surfaces under ``version="v2"``.


class _FakeChunk(AIMessageChunk):
    """Stand-in for ``AIMessageChunk`` — only ``content`` is read.

    Subclasses the real ``AIMessageChunk`` so ``_invoke_agent_once``'s
    ``isinstance(chunk, AIMessageChunk)`` guard passes (the same guard
    ``stream_agent`` uses).
    """

    def __init__(self, content: str) -> None:
        super().__init__(content=content)


class _FakeOutput:
    """Stand-in for the message object carried on ``on_chat_model_end``.

    Only ``usage_metadata`` is read by ``_invoke_agent_once``.
    """

    def __init__(self, usage: dict | None) -> None:
        self.usage_metadata = usage


class _FakeInvokeResult:
    """Stand-in for the message returned by ``ChatOpenAI.ainvoke``."""

    def __init__(self, content: str, usage: dict | None) -> None:
        self.content = content
        self.usage_metadata = usage


class _FakeLLM:
    """Fake ``ChatOpenAI`` instance.

    Carries the model name (for ``create_react_agent`` dispatch) and a
    callable ``ainvoke`` used by the synthesize path. The synthesize path
    is configured separately from the fan-out path because they read
    different LLM entry points.
    """

    def __init__(self, model: str, invoke_result=None, invoke_exc=None) -> None:
        self.model = model
        self._invoke_result = invoke_result
        self._invoke_exc = invoke_exc

    async def ainvoke(self, _prompt, *_args, **_kwargs):  # noqa: ANN001
        if self._invoke_exc is not None:
            raise self._invoke_exc
        return self._invoke_result


class _FakeAgent:
    """Scripted ``astream_events(version="v2")`` emitter.

    ``rounds`` is a list of (text, usage) tuples — one entry per LLM call
    within this turn. A ReAct agent often calls the model several times
    (think → tool → think again); we emit each round's stream chunks then
    its end-event so the accumulator sees every call.
    """

    def __init__(self, rounds: list[tuple[str, dict]]) -> None:
        self._rounds = rounds

    async def astream_events(self, *_args, **_kwargs):  # noqa: ANN003 - mirror SDK
        for text, usage in self._rounds:
            # Stream the text in two pieces so the content-concatenation
            # path is exercised, not just a single setattr.
            half = len(text) // 2
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": _FakeChunk(text[:half])},
            }
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": _FakeChunk(text[half:])},
            }
            yield {
                "event": "on_chat_model_end",
                "data": {"output": _FakeOutput(usage)},
            }


class _HangingAgent:
    """Never yields an event — simulates a stalled provider."""

    def __init__(self, delay: float = 30.0) -> None:
        self._delay = delay

    async def astream_events(self, *_args, **_kwargs):  # noqa: ANN003
        await asyncio.sleep(self._delay)
        yield {}  # pragma: no cover - unreachable


class _RaisingAgent:
    """Raises mid-stream — simulates a provider error for one agent."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def astream_events(self, *_args, **_kwargs):  # noqa: ANN003
        raise self._exc
        yield {}  # pragma: no cover - unreachable


class _SlowAgent(_FakeAgent):
    """Fake agent that sleeps before emitting — used for parallelism tests."""

    def __init__(self, rounds: list[tuple[str, dict]], delay: float) -> None:
        super().__init__(rounds)
        self._delay = delay

    async def astream_events(self, *_args, **_kwargs):  # noqa: ANN003
        await asyncio.sleep(self._delay)
        async for ev in super().astream_events(*_args, **_kwargs):
            yield ev


def _agent_row(
    *,
    id: str = "agt-A",
    name: str = "Agent A",
    model: str = "deepseek-chat",
    max_tokens: int | None = None,
    temperature: float = 0.7,
    top_p: float | None = None,
    system_prompt: str = "你是助手",
):
    """Build a lightweight Agent stand-in (no DB needed for these unit tests).

    ``_invoke_agent_once`` only reads ``id`` / ``name`` / ``model`` /
    ``system_prompt`` / ``temperature`` / ``max_tokens`` / ``top_p`` from the
    row, so a ``SimpleNamespace`` is sufficient and keeps the test offline.
    """
    from types import SimpleNamespace

    return SimpleNamespace(
        id=id,
        name=name,
        model=model,
        system_prompt=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
    )


class _MockConfig:
    """Bundle of per-model behaviors installed into ``graph`` for one test.

    ``fanout[model]``  → fake ReAct agent for the fan-out call
    ``synth[model]``   → fake ``ainvoke`` result (or exception) for synthesize

    A model used for both (e.g. ``agents[0].model`` when no override) can
    appear in both maps — the fan-out uses ``create_react_agent``, the
    synthesize uses ``ainvoke`` directly, so they don't collide.
    """

    def __init__(self) -> None:
        self.fanout: dict[str, object] = {}
        self.synth: dict[str, object] = {}  # value: _FakeInvokeResult | Exception


def _install_mock(monkeypatch, config: _MockConfig) -> None:
    """Patch ``ChatOpenAI`` + ``create_react_agent`` per ``config``."""
    from app.agents import graph as graph_module

    def _fake_chat_openai(**kwargs):  # noqa: ANN201 - opaque token
        model = kwargs.get("model")
        # If this model has a synthesize result, attach it; otherwise default
        # to a no-op ainvoke (won't be called unless synthesize uses it).
        if model in config.synth:
            entry = config.synth[model]
            if isinstance(entry, Exception):
                return _FakeLLM(model, invoke_exc=entry)
            return _FakeLLM(model, invoke_result=entry)
        return _FakeLLM(model)

    def _fake_create_react_agent(llm, *_args, **_kwargs):  # noqa: ANN001
        return config.fanout[llm.model]

    monkeypatch.setattr(graph_module, "ChatOpenAI", _fake_chat_openai)
    monkeypatch.setattr(graph_module, "create_react_agent", _fake_create_react_agent)


def _usage(inp: int, out: int) -> dict:
    return {
        "input_tokens": inp,
        "output_tokens": out,
        "total_tokens": inp + out,
    }


def _invoke_result(text: str, usage: dict) -> _FakeInvokeResult:
    return _FakeInvokeResult(content=text, usage=usage)


# --------------------------------------------------------------- _fallback_synthesis


def test_fallback_synthesis_combines_completed_fragments():
    """Completed fragments are joined under agent-name headings."""
    frags = [
        {"agent_name": "A", "status": "completed", "snippet": "答案甲"},
        {"agent_name": "B", "status": "completed", "snippet": "答案乙"},
    ]
    out = _fallback_synthesis(frags)
    assert "## A\n答案甲" in out
    assert "## B\n答案乙" in out
    assert "---" in out  # separator between fragments


def test_fallback_synthesis_marks_failed_fragments():
    """Failed fragments surface a bracketed failure notice, not their snippet."""
    frags = [
        {"agent_name": "A", "status": "completed", "snippet": "ok"},
        {"agent_name": "B", "status": "failed", "snippet": "", "error": "timeout"},
    ]
    out = _fallback_synthesis(frags)
    assert "## A\nok" in out
    assert "## B" in out
    assert "[此 agent 失败: timeout]" in out


def test_fallback_synthesis_empty_list_returns_empty_string():
    assert _fallback_synthesis([]) == ""


# --------------------------------------------------------------- composite_query happy path


@pytest.mark.asyncio
async def test_composite_query_three_agents_all_succeed(monkeypatch):
    """3 agents fan out in parallel; synthesis + 3 fragments + 4th usage row."""
    cfg = _MockConfig()
    # Fan-out: each model has its own scripted reply + usage.
    cfg.fanout["m-A"] = _FakeAgent([("回答甲", _usage(10, 5))])
    cfg.fanout["m-B"] = _FakeAgent([("回答乙", _usage(20, 7))])
    cfg.fanout["m-C"] = _FakeAgent([("回答丙", _usage(30, 9))])
    # Synthesize: m-synth is the merge model (via override).
    cfg.synth["m-synth"] = _invoke_result("综合: 甲乙丙", _usage(100, 50))
    _install_mock(monkeypatch, cfg)

    agents = [_agent_row(id="agt-A", name="A", model="m-A"),
              _agent_row(id="agt-B", name="B", model="m-B"),
              _agent_row(id="agt-C", name="C", model="m-C")]

    result = await composite_query(
        user_id="usr-x", tenant_id="tnt-x", db=None,
        api_key="k", base_url="http://x", agents=agents, message="问题",
        synthesize_model="m-synth",
    )

    assert set(result.keys()) == {
        "synthesis", "fragments", "synthesize_usage", "usage_total",
    }
    assert result["synthesis"] == "综合: 甲乙丙"
    assert len(result["fragments"]) == 3
    statuses = [f["status"] for f in result["fragments"]]
    assert statuses == ["completed", "completed", "completed"]
    # Each fragment carries its agent's tokens.
    by_id = {f["agent_id"]: f for f in result["fragments"]}
    assert by_id["agt-A"]["total_tokens"] == 15
    assert by_id["agt-B"]["total_tokens"] == 27
    assert by_id["agt-C"]["total_tokens"] == 39
    # synthesize_usage reports the synthesize call's tokens.
    assert result["synthesize_usage"]["total_tokens"] == 150
    assert result["synthesize_usage"]["model"] == "m-synth"
    # usage_total = Σ fragments + synthesize = 15+27+39+150 = 231
    assert result["usage_total"]["total_tokens"] == 231
    assert result["usage_total"]["input_tokens"] == 10 + 20 + 30 + 100
    assert result["usage_total"]["output_tokens"] == 5 + 7 + 9 + 50


@pytest.mark.asyncio
async def test_composite_query_synthesize_defaults_to_first_agent_model(monkeypatch):
    """Without an override, synthesize uses agents[0].model."""
    cfg = _MockConfig()
    cfg.fanout["m-A"] = _FakeAgent([("甲", _usage(1, 1))])
    cfg.fanout["m-B"] = _FakeAgent([("乙", _usage(2, 2))])
    # m-A doubles as the synthesize model (default path).
    cfg.synth["m-A"] = _invoke_result("合并", _usage(5, 5))
    _install_mock(monkeypatch, cfg)

    agents = [_agent_row(id="agt-A", name="A", model="m-A"),
              _agent_row(id="agt-B", name="B", model="m-B")]
    result = await composite_query(
        user_id="usr-x", tenant_id="tnt-x", db=None,
        api_key="k", base_url="http://x", agents=agents, message="问题",
    )

    assert result["synthesize_usage"]["model"] == "m-A"
    assert result["synthesis"] == "合并"


@pytest.mark.asyncio
async def test_composite_query_one_agent_failure_is_isolated(monkeypatch):
    """One agent raises; its fragment is failed, others complete, synthesis runs."""
    cfg = _MockConfig()
    cfg.fanout["m-A"] = _FakeAgent([("甲", _usage(10, 5))])
    cfg.fanout["m-B"] = _RaisingAgent(RuntimeError("boom"))
    cfg.fanout["m-C"] = _FakeAgent([("丙", _usage(30, 9))])
    cfg.synth["m-synth"] = _invoke_result("综合", _usage(1, 1))
    _install_mock(monkeypatch, cfg)

    agents = [_agent_row(id="agt-A", name="A", model="m-A"),
              _agent_row(id="agt-B", name="B", model="m-B"),
              _agent_row(id="agt-C", name="C", model="m-C")]

    result = await composite_query(
        user_id="usr-x", tenant_id="tnt-x", db=None,
        api_key="k", base_url="http://x", agents=agents, message="问题",
        synthesize_model="m-synth",
    )

    frags = {f["agent_id"]: f for f in result["fragments"]}
    assert frags["agt-A"]["status"] == "completed"
    assert frags["agt-C"]["status"] == "completed"
    assert frags["agt-B"]["status"] == "failed"
    assert "boom" in frags["agt-B"]["error"]
    assert result["synthesis"] == "综合"
    # Failed agent contributes zero tokens to the aggregate.
    assert result["usage_total"]["total_tokens"] == 15 + 39 + 2


@pytest.mark.asyncio
async def test_composite_query_synthesize_failure_degrades(monkeypatch):
    """When the synthesize LLM call fails, synthesis falls back to fragments."""
    cfg = _MockConfig()
    cfg.fanout["m-A"] = _FakeAgent([("甲答", _usage(10, 5))])
    cfg.fanout["m-B"] = _FakeAgent([("乙答", _usage(20, 7))])
    # Synthesize call raises.
    cfg.synth["m-synth"] = RuntimeError("synth boom")
    _install_mock(monkeypatch, cfg)

    agents = [_agent_row(id="agt-A", name="A", model="m-A"),
              _agent_row(id="agt-B", name="B", model="m-B")]

    result = await composite_query(
        user_id="usr-x", tenant_id="tnt-x", db=None,
        api_key="k", base_url="http://x", agents=agents, message="问题",
        synthesize_model="m-synth",
    )

    # Synthesis degraded to the fallback concatenation, not an exception.
    assert "## A" in result["synthesis"]
    assert "甲答" in result["synthesis"]
    assert "## B" in result["synthesis"]
    assert "乙答" in result["synthesis"]
    # synthesize_usage is zeroed on degradation (no tokens consumed).
    assert result["synthesize_usage"]["total_tokens"] == 0
    assert result["synthesize_usage"]["input_tokens"] == 0
    assert result["synthesize_usage"]["output_tokens"] == 0
    assert result["synthesize_usage"]["model"] == "m-synth"
    # usage_total only counts the succeeded agent fragments.
    assert result["usage_total"]["total_tokens"] == 15 + 27


# --------------------------------------------------------------- multi-round usage


@pytest.mark.asyncio
async def test_composite_query_multi_round_usage_accumulates(monkeypatch):
    """A ReAct agent calling the LLM twice reports the SUM of both rounds.

    This is the core reason ``_invoke_agent_once`` uses ``astream_events``
    rather than ``ainvoke`` — ``ainvoke`` would only return the final round's
    usage and silently under-count. The fake agent emits two rounds.
    """
    cfg = _MockConfig()
    cfg.fanout["m-A"] = _FakeAgent([
        ("先想", _usage(100, 10)),   # round 1: reasoning before tool call
        ("再答", _usage(50, 20)),    # round 2: answer after tool returns
    ])
    cfg.synth["m-synth"] = _invoke_result("综合", _usage(1, 1))
    _install_mock(monkeypatch, cfg)

    agents = [_agent_row(id="agt-A", name="A", model="m-A")]
    result = await composite_query(
        user_id="usr-x", tenant_id="tnt-x", db=None,
        api_key="k", base_url="http://x", agents=agents, message="问题",
        synthesize_model="m-synth",
    )

    frag = result["fragments"][0]
    # 100+50 input, 10+20 output, 180 total — NOT just the last round (70).
    assert frag["input_tokens"] == 150
    assert frag["output_tokens"] == 30
    assert frag["total_tokens"] == 180
    # Snippet is the concatenation of both rounds' text.
    assert frag["snippet"] == "先想再答"


# --------------------------------------------------------------- timeout fail-open


@pytest.mark.asyncio
async def test_composite_query_timeout_keeps_completed_fragments(monkeypatch):
    """A stalled agent is abandoned on timeout; completed ones survive.

    Uses the real ``asyncio.wait_for`` path with a tiny timeout so the
    fail-open branch (except TimeoutError: pass) is exercised.
    """
    cfg = _MockConfig()
    cfg.fanout["m-A"] = _FakeAgent([("甲", _usage(10, 5))])
    cfg.fanout["m-B"] = _HangingAgent(delay=30.0)
    cfg.synth["m-synth"] = _invoke_result("综合", _usage(1, 1))
    _install_mock(monkeypatch, cfg)

    agents = [_agent_row(id="agt-A", name="A", model="m-A"),
              _agent_row(id="agt-B", name="B", model="m-B")]

    # Force a tiny fan-out timeout (default N*30+60=120s is too long for a
    # unit test). composite_query accepts ``fanout_timeout``.
    result = await composite_query(
        user_id="usr-x", tenant_id="tnt-x", db=None,
        api_key="k", base_url="http://x", agents=agents, message="问题",
        synthesize_model="m-synth", fanout_timeout=0.2,
    )

    frags = {f["agent_id"]: f for f in result["fragments"]}
    # A completed before the timeout; its fragment survived in the outer list.
    assert frags["agt-A"]["status"] == "completed"
    assert frags["agt-A"]["snippet"] == "甲"
    # B was abandoned — no fragment for it (timeout cancelled its task before
    # the per-agent try/except could append a failed row).
    assert "agt-B" not in frags
    # Synthesis still ran on the surviving fragment.
    assert "综合" in result["synthesis"]


# --------------------------------------------------------------- fan-out parallelism


@pytest.mark.asyncio
async def test_composite_query_fan_out_runs_in_parallel(monkeypatch):
    """3 agents each sleeping 0.1s finish in well under 3×0.1s (serial would)."""
    cfg = _MockConfig()
    cfg.fanout["m-A"] = _SlowAgent([("甲", _usage(1, 1))], delay=0.1)
    cfg.fanout["m-B"] = _SlowAgent([("乙", _usage(1, 1))], delay=0.1)
    cfg.fanout["m-C"] = _SlowAgent([("丙", _usage(1, 1))], delay=0.1)
    cfg.synth["m-synth"] = _invoke_result("综合", _usage(1, 1))
    _install_mock(monkeypatch, cfg)

    agents = [_agent_row(id="agt-A", name="A", model="m-A"),
              _agent_row(id="agt-B", name="B", model="m-B"),
              _agent_row(id="agt-C", name="C", model="m-C")]

    loop = asyncio.get_event_loop()
    t0 = loop.time()
    await composite_query(
        user_id="usr-x", tenant_id="tnt-x", db=None,
        api_key="k", base_url="http://x", agents=agents, message="问题",
        synthesize_model="m-synth",
    )
    elapsed = loop.time() - t0
    # Parallel: ~0.1s + tiny overhead. Serial would be ~0.3s+. 0.25s cutoff
    # separates them comfortably on a CI runner.
    assert elapsed < 0.25, f"fan-out took {elapsed:.3f}s — not parallel"


# --------------------------------------------------------------- token caps


def _install_token_cap_spy(monkeypatch, captured: dict) -> None:
    """Spy on ``_build_llm_kwargs`` to record the max_tokens passed per call.

    The spy forwards to the real implementation so ``ChatOpenAI`` still gets
    a valid kwargs dict (the mock ``ChatOpenAI`` ignores it, but the contract
    must hold in case a future reader copies this pattern to a real-LLM test).
    """
    from app.agents import graph as graph_module

    real_build = graph_module._build_llm_kwargs

    def _spy(**kwargs):
        captured.setdefault("calls", []).append(kwargs)
        return real_build(**kwargs)

    monkeypatch.setattr(graph_module, "_build_llm_kwargs", _spy)


@pytest.mark.asyncio
async def test_composite_query_token_cap_none_falls_back_to_300(monkeypatch):
    """An agent with max_tokens=None gets 300 (composite cost-control default)."""
    cfg = _MockConfig()
    cfg.fanout["m-A"] = _FakeAgent([("甲", _usage(1, 1))])
    cfg.synth["m-synth"] = _invoke_result("综合", _usage(1, 1))
    _install_mock(monkeypatch, cfg)

    captured: dict = {}
    _install_token_cap_spy(monkeypatch, captured)

    agents = [_agent_row(id="agt-A", name="A", model="m-A", max_tokens=None)]
    await composite_query(
        user_id="usr-x", tenant_id="tnt-x", db=None,
        api_key="k", base_url="http://x", agents=agents, message="问题",
        synthesize_model="m-synth",
    )

    # First _build_llm_kwargs call is the fan-out agent; it should use 300.
    agent_calls = [c for c in captured["calls"] if c.get("model") == "m-A"]
    assert agent_calls, "fan-out agent call not recorded"
    assert agent_calls[0]["max_tokens"] == 300


@pytest.mark.asyncio
async def test_composite_query_token_cap_explicit_value_passes_through(monkeypatch):
    """An agent with max_tokens=200 keeps 200 (explicit config wins over fallback)."""
    cfg = _MockConfig()
    cfg.fanout["m-A"] = _FakeAgent([("甲", _usage(1, 1))])
    cfg.synth["m-synth"] = _invoke_result("综合", _usage(1, 1))
    _install_mock(monkeypatch, cfg)

    captured: dict = {}
    _install_token_cap_spy(monkeypatch, captured)

    agents = [_agent_row(id="agt-A", name="A", model="m-A", max_tokens=200)]
    await composite_query(
        user_id="usr-x", tenant_id="tnt-x", db=None,
        api_key="k", base_url="http://x", agents=agents, message="问题",
        synthesize_model="m-synth",
    )

    agent_calls = [c for c in captured["calls"] if c.get("model") == "m-A"]
    assert agent_calls[0]["max_tokens"] == 200


@pytest.mark.asyncio
async def test_composite_query_token_cap_1000_passes_through(monkeypatch):
    """An agent with max_tokens=1000 keeps 1000 (no clamping to the 300 default)."""
    cfg = _MockConfig()
    cfg.fanout["m-A"] = _FakeAgent([("甲", _usage(1, 1))])
    cfg.synth["m-synth"] = _invoke_result("综合", _usage(1, 1))
    _install_mock(monkeypatch, cfg)

    captured: dict = {}
    _install_token_cap_spy(monkeypatch, captured)

    agents = [_agent_row(id="agt-A", name="A", model="m-A", max_tokens=1000)]
    await composite_query(
        user_id="usr-x", tenant_id="tnt-x", db=None,
        api_key="k", base_url="http://x", agents=agents, message="问题",
        synthesize_model="m-synth",
    )

    agent_calls = [c for c in captured["calls"] if c.get("model") == "m-A"]
    assert agent_calls[0]["max_tokens"] == 1000
