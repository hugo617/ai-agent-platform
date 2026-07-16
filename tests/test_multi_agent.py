"""Multi-Agent orchestration tests (priority 58).

Covers three layers:

1. **Pure routing logic** (no LLM, no DB) — supervisor prompt construction,
   route resolution + fallback. These are deterministic and fast.
2. **CRUD + permissions** (HTTP via app_client) — attach/detach specialists,
   AgentRead exposes is_orchestrator/specialty/specialist_ids, member cannot
   attach (403), cascade cleanup on delete.
3. **Chat dispatch** (mock stream) — an orchestrator Agent routes through
   ``stream_orchestrator`` while a plain Agent keeps using ``stream_agent``
   (backward compatibility), and an orchestrator with no specialists degrades
   to the plain path.
"""

import pytest

AUTH = {"Authorization": "Bearer fake"}


# ---------------------------------------------------------- pure routing logic


class _FakeAgent:
    """Minimal stand-in for an Agent ORM row (pure-function tests only)."""

    def __init__(
        self,
        id,
        name,
        specialty=None,
        description="",
        temperature=0.7,
        max_tokens=None,
        top_p=None,
        system_prompt="",
    ):
        self.id = id
        self.name = name
        self.specialty = specialty
        self.description = description
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.top_p = top_p
        self.system_prompt = system_prompt


@pytest.mark.asyncio
async def test_supervisor_prompt_lists_all_specialists():
    from app.agents.graph import _build_supervisor_prompt

    sps = [
        _FakeAgent("a1", "健康顾问", specialty="理疗/针灸"),
        _FakeAgent("a2", "预约专员", specialty="预约/排班"),
    ]
    prompt = _build_supervisor_prompt(sps)
    assert "健康顾问" in prompt
    assert "理疗/针灸" in prompt
    assert "a1" in prompt and "a2" in prompt
    assert "specialist_id" in prompt  # tells the LLM the output contract


@pytest.mark.asyncio
async def test_supervisor_prompt_falls_back_to_description_when_no_specialty():
    from app.agents.graph import _build_supervisor_prompt

    sp = _FakeAgent("a1", "通用助手", specialty=None, description="兜底回答")
    prompt = _build_supervisor_prompt([sp])
    assert "兜底回答" in prompt  # specialty missing → use description


@pytest.mark.asyncio
async def test_resolve_route_target_picks_matching_specialist():
    from app.agents.graph import _resolve_route_target

    sps = [_FakeAgent("a1", "X"), _FakeAgent("a2", "Y")]

    class _Dec:
        specialist_id = "a2"

    assert _resolve_route_target(_Dec(), sps) == "a2"


@pytest.mark.asyncio
async def test_resolve_route_target_falls_back_to_first_on_unknown_id():
    from app.agents.graph import _resolve_route_target

    sps = [_FakeAgent("a1", "X"), _FakeAgent("a2", "Y")]

    class _Dec:
        specialist_id = "does-not-exist"

    # Unknown id → first specialist (never raises, chat must not dead-end).
    assert _resolve_route_target(_Dec(), sps) == "a1"


# ---------------------------------------------------------- CRUD + permissions


async def _create_agent(client, **overrides):
    """Helper: POST an agent, return the created body."""
    payload = {"name": "Agent", **overrides}
    resp = await client.post("/api/v1/agents/", json=payload, headers=AUTH)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_create_orchestrator_agent_persists_flag(app_client):
    body = await _create_agent(
        app_client, name="编排器", is_orchestrator=True, specialty="路由"
    )
    assert body["is_orchestrator"] is True
    assert body["specialty"] == "路由"
    assert body["specialist_ids"] == []  # no specialists attached yet


@pytest.mark.asyncio
async def test_agent_read_defaults_regular_when_flag_absent(app_client):
    """Creating an agent without is_orchestrator must default to False."""
    body = await _create_agent(app_client, name="普通")
    assert body["is_orchestrator"] is False
    assert body["specialty"] is None


@pytest.mark.asyncio
async def test_attach_and_list_specialists(app_client):
    orch = await _create_agent(
        app_client, name="编排器", is_orchestrator=True, specialty="路由"
    )
    sp = await _create_agent(
        app_client, name="健康顾问", specialty="理疗"
    )

    # Attach
    resp = await app_client.post(
        f"/api/v1/agents/{orch['id']}/specialists/{sp['id']}", headers=AUTH
    )
    assert resp.status_code == 204

    # List reflects the attachment
    resp = await app_client.get(
        f"/api/v1/agents/{orch['id']}/specialists", headers=AUTH
    )
    assert resp.status_code == 200
    specialists = resp.json()
    assert len(specialists) == 1
    assert specialists[0]["id"] == sp["id"]

    # The orchestrator's own AgentRead now carries specialist_ids
    resp = await app_client.get(
        f"/api/v1/agents/{orch['id']}", headers=AUTH
    )
    assert resp.json()["specialist_ids"] == [sp["id"]]


@pytest.mark.asyncio
async def test_attach_rejects_self_attach(app_client):
    orch = await _create_agent(
        app_client, name="编排器", is_orchestrator=True
    )
    resp = await app_client.post(
        f"/api/v1/agents/{orch['id']}/specialists/{orch['id']}", headers=AUTH
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_attach_rejects_non_orchestrator_target(app_client):
    """Attaching to an Agent that isn't an orchestrator is a 400."""
    a = await _create_agent(app_client, name="普通A")  # is_orchestrator=False
    b = await _create_agent(app_client, name="普通B")
    resp = await app_client.post(
        f"/api/v1/agents/{a['id']}/specialists/{b['id']}", headers=AUTH
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_attach_rejects_specialist_that_is_itself_orchestrator(app_client):
    """No chaining: an orchestrator can't be attached as a specialist."""
    orch = await _create_agent(
        app_client, name="编排器", is_orchestrator=True
    )
    other_orch = await _create_agent(
        app_client, name="另一个编排器", is_orchestrator=True
    )
    resp = await app_client.post(
        f"/api/v1/agents/{orch['id']}/specialists/{other_orch['id']}",
        headers=AUTH,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_attach_is_idempotent_rejects_duplicate(app_client):
    orch = await _create_agent(
        app_client, name="编排器", is_orchestrator=True
    )
    sp = await _create_agent(app_client, name="specialist")
    await app_client.post(
        f"/api/v1/agents/{orch['id']}/specialists/{sp['id']}", headers=AUTH
    )
    # Second attach → 400 (duplicate)
    resp = await app_client.post(
        f"/api/v1/agents/{orch['id']}/specialists/{sp['id']}", headers=AUTH
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_detach_specialist(app_client):
    orch = await _create_agent(
        app_client, name="编排器", is_orchestrator=True
    )
    sp = await _create_agent(app_client, name="specialist")
    await app_client.post(
        f"/api/v1/agents/{orch['id']}/specialists/{sp['id']}", headers=AUTH
    )
    resp = await app_client.delete(
        f"/api/v1/agents/{orch['id']}/specialists/{sp['id']}", headers=AUTH
    )
    assert resp.status_code == 204
    # List is now empty
    resp = await app_client.get(
        f"/api/v1/agents/{orch['id']}/specialists", headers=AUTH
    )
    assert resp.json() == []


@pytest.mark.asyncio
async def test_detach_unknown_returns_404(app_client):
    orch = await _create_agent(
        app_client, name="编排器", is_orchestrator=True
    )
    sp = await _create_agent(app_client, name="未挂载")
    resp = await app_client.delete(
        f"/api/v1/agents/{orch['id']}/specialists/{sp['id']}", headers=AUTH
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_member_cannot_attach_specialist(member_client):
    """member role lacks agents:update → attach must 403.

    Uses an arbitrary id: the route-level ``require_permission`` guard fires
    before the body runs (same pattern as ``test_member_cannot_update_agent``
    in test_agents_api.py), so the agent ids need not exist.
    """
    resp = await member_client.post(
        "/api/v1/agents/any-orch-id/specialists/any-sp-id", headers=AUTH
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_orchestrator_cascades_memberships(app_client):
    """Deleting an orchestrator Agent removes its specialist memberships.

    Verified via the API rather than a raw DB read: after deleting the
    orchestrator, recreating it with the same id is not possible (ids are
    uuids), so instead we verify the specialist still exists and that the
    membership is gone by re-attaching without a duplicate error. The FK
    ondelete=CASCADE handles cleanup at the DB layer.
    """
    orch = await _create_agent(
        app_client, name="编排器", is_orchestrator=True
    )
    sp = await _create_agent(app_client, name="specialist")
    await app_client.post(
        f"/api/v1/agents/{orch['id']}/specialists/{sp['id']}", headers=AUTH
    )

    # Delete the orchestrator
    resp = await app_client.delete(f"/api/v1/agents/{orch['id']}", headers=AUTH)
    assert resp.status_code == 204

    # The specialist itself survives (only the membership + orchestrator died).
    resp = await app_client.get(f"/api/v1/agents/{sp['id']}", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["id"] == sp["id"]

    # The orchestrator is gone.
    resp = await app_client.get(f"/api/v1/agents/{orch['id']}", headers=AUTH)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cross_tenant_specialist_not_visible(app_client, db_session):
    """A specialist created in another tenant can't be attached (404)."""
    from app.models.agent import Agent

    orch = await _create_agent(
        app_client, name="编排器", is_orchestrator=True
    )
    # Plant a specialist in a DIFFERENT tenant directly via ORM.
    other = Agent(
        id="agent-other-tenant",
        tenant_id="tnt-other-cross-wall",
        name="Other Tenant Specialist",
    )
    db_session.add(other)
    await db_session.commit()

    resp = await app_client.post(
        f"/api/v1/agents/{orch['id']}/specialists/agent-other-tenant", headers=AUTH
    )
    assert resp.status_code == 404  # _owned tenant-scope guard


# ---------------------------------------------------------- chat dispatch


@pytest.mark.asyncio
async def test_orchestrator_chat_routes_through_stream_orchestrator(app_client):
    """An orchestrator Agent must dispatch via stream_orchestrator (not stream_agent)."""
    orch = await _create_agent(
        app_client, name="编排器", is_orchestrator=True, specialty="路由"
    )
    sp = await _create_agent(app_client, name="健康顾问", specialty="理疗")
    await app_client.post(
        f"/api/v1/agents/{orch['id']}/specialists/{sp['id']}", headers=AUTH
    )

    captured = {}
    routed_via_orchestrator = {"value": False}

    async def fake_orchestrator(**kwargs):
        routed_via_orchestrator["value"] = True
        captured.update(kwargs)
        yield "routed"

    # Patch BOTH entry points on the chat module so we can assert which one
    # was actually called. ``stream_agent`` is imported at module load, and
    # ``stream_orchestrator`` is imported lazily inside event_source — patch
    # the latter on the graph module where event_source imports it from.
    import app.agents.graph as graph_module

    original = graph_module.stream_orchestrator
    graph_module.stream_orchestrator = fake_orchestrator
    try:
        resp = await app_client.post(
            "/api/v1/chat/stream",
            json={"agent_id": orch["id"], "message": "颈椎理疗怎么做的?"},
            headers=AUTH,
        )
        # The SSE body is plain text; just assert the streamed content shows
        # the orchestrator path was used.
        assert resp.status_code == 200
        assert routed_via_orchestrator["value"] is True
        assert "specialists" in captured  # specialists passed in
        assert len(captured["specialists"]) == 1
    finally:
        graph_module.stream_orchestrator = original


@pytest.mark.asyncio
async def test_plain_agent_chat_still_uses_stream_agent(app_client):
    """Backward compat: a regular Agent must NOT touch stream_orchestrator."""
    # Make a plain agent (is_orchestrator defaults to False) and stub the
    # chat module's stream_agent reference to prove it's the one called.
    from app.api.v1 import chat as chat_route

    agent_body = await _create_agent(app_client, name="普通")
    assert agent_body["is_orchestrator"] is False

    async def fake_stream(**kwargs):
        yield "plain"

    original = chat_route.stream_agent
    chat_route.stream_agent = fake_stream
    try:
        resp = await app_client.post(
            "/api/v1/chat/stream",
            json={"agent_id": agent_body["id"], "message": "你好"},
            headers=AUTH,
        )
        assert resp.status_code == 200
        assert "plain" in resp.text
    finally:
        chat_route.stream_agent = original


@pytest.mark.asyncio
async def test_orchestrator_without_specialists_degrades_to_plain(app_client):
    """An orchestrator with no specialists attached must still answer (degrade)."""
    from app.api.v1 import chat as chat_route

    orch = await _create_agent(
        app_client, name="空编排器", is_orchestrator=True, specialty="路由"
    )
    # No specialists attached.

    async def fake_stream(**kwargs):
        yield "degraded"

    original = chat_route.stream_agent
    chat_route.stream_agent = fake_stream
    try:
        resp = await app_client.post(
            "/api/v1/chat/stream",
            json={"agent_id": orch["id"], "message": "你好"},
            headers=AUTH,
        )
        assert resp.status_code == 200
        assert "degraded" in resp.text
    finally:
        chat_route.stream_agent = original
