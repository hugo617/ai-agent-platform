"""Dashboard analytics API tests — entity stats + trends + HQ overview.

Covers:
- /agents/statistics, /conversations/statistics, /customers/statistics: store
  counts + super_admin cross-tenant + 403 for forbidden roles.
- /dashboard/trends: store-scoped daily points; super_admin cross-tenant
  aggregate; days clamp; days with no activity filled as zeros.
- /dashboard/overview: super_admin platform totals + per-tenant Top N;
  non-super_admin → 403.

Trend seeding uses db_session (not the chat API) because deterministic dates
matter — the chat endpoint stamps created_at=now(), so we set created_at
explicitly to place rows in the right day buckets.
"""

from datetime import UTC, datetime, timedelta

import pytest

AUTH = {"Authorization": "Bearer fake"}


# ----------------------------------------------------- entity statistics


@pytest.mark.asyncio
async def test_agent_statistics_store(app_client):
    """Store /agents/statistics counts this tenant's agents."""
    await app_client.post("/api/v1/agents/", json={"name": "A1"}, headers=AUTH)
    await app_client.post("/api/v1/agents/", json={"name": "A2"}, headers=AUTH)
    resp = await app_client.get("/api/v1/agents/statistics", headers=AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    # Agents have no status column → active mirrors total.
    assert body["active"] == 2


@pytest.mark.asyncio
async def test_agent_statistics_super_admin_cross_tenant(
    super_admin_client, db_session
):
    """super_admin /agents/statistics counts agents across ALL tenants."""
    from app.models.agent import Agent
    from app.models.tenant import Tenant

    # Own-tenant agent via API (under super_admin_client's tenant).
    await super_admin_client.post(
        "/api/v1/agents/", json={"name": "Own"}, headers=AUTH
    )
    # Another tenant's agent, seeded directly.
    other = "tnt-agent-other"
    db_session.add(Tenant(id=other, name="Other"))
    db_session.add(Agent(id="agent-x", tenant_id=other, name="Other Bot"))
    await db_session.commit()

    resp = await super_admin_client.get("/api/v1/agents/statistics", headers=AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Own (1) + other (1).
    assert body["total"] == 2


@pytest.mark.asyncio
async def test_conversation_statistics_scoped_to_caller_tenant(
    app_client, test_env, db_session
):
    """Store counts only the caller's tenant; cross-tenant rows are excluded."""
    from app.models.agent import Conversation
    from app.models.tenant import Tenant

    now = datetime.now(UTC)
    # Own tenant: 2 conversations (1 in 7d, 1 old).
    db_session.add(
        Conversation(
            tenant_id=test_env.tenant_id,
            agent_id="a1",
            user_id="u1",
            title="own-recent",
            created_at=now - timedelta(days=1),
        )
    )
    db_session.add(
        Conversation(
            tenant_id=test_env.tenant_id,
            agent_id="a1",
            user_id="u1",
            title="own-old",
            created_at=now - timedelta(days=40),
        )
    )
    # Other tenant: should NOT count.
    other = "tnt-conv-other"
    db_session.add(Tenant(id=other, name="Other"))
    db_session.add(
        Conversation(
            tenant_id=other,
            agent_id="a1",
            user_id="u1",
            title="other",
            created_at=now - timedelta(days=1),
        )
    )
    await db_session.commit()

    resp = await app_client.get("/api/v1/conversations/statistics", headers=AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2  # own-recent + own-old
    assert body["last_7d"] == 1
    assert body["last_30d"] == 1


@pytest.mark.asyncio
async def test_conversation_statistics_super_admin_cross_tenant(
    super_admin_client, test_env, db_session
):
    """super_admin /conversations/statistics aggregates across tenants."""
    from app.models.agent import Conversation
    from app.models.tenant import Tenant

    now = datetime.now(UTC)
    other = "tnt-conv-sa-other"
    db_session.add(Tenant(id=other, name="OtherSA"))
    # One in own tenant, one in the other tenant (both recent).
    db_session.add(
        Conversation(
            tenant_id=test_env.tenant_id,
            agent_id="a1",
            user_id="u1",
            title="own",
            created_at=now - timedelta(days=1),
        )
    )
    db_session.add(
        Conversation(
            tenant_id=other,
            agent_id="a1",
            user_id="u1",
            title="other",
            created_at=now - timedelta(days=1),
        )
    )
    await db_session.commit()

    resp = await super_admin_client.get(
        "/api/v1/conversations/statistics", headers=AUTH
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2  # both tenants
    assert body["last_7d"] == 2


@pytest.mark.asyncio
async def test_customer_statistics_store(app_client):
    """Store /customers/statistics counts this tenant's profiles."""
    await app_client.post(
        "/api/v1/customers/profiles/",
        json={"identity_key": "13800000201", "name": "Active1"},
        headers=AUTH,
    )
    await app_client.post(
        "/api/v1/customers/profiles/",
        json={"identity_key": "13800000202", "name": "Lost", "status": "lost"},
        headers=AUTH,
    )
    resp = await app_client.get("/api/v1/customers/statistics", headers=AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    assert body["active"] == 1  # only the status='active' one
    assert body["last_7d_new"] == 2  # both created just now


@pytest.mark.asyncio
async def test_customer_statistics_super_admin_identity_count(
    super_admin_client, db_session, test_env
):
    """super_admin /customers/statistics counts global identities (not profiles).

    Two stores sharing one identity → 1 Customer (identity), 2 profiles. The
    store card would count 2 profiles, but the HQ card counts 1 identity.
    """
    from app.models.customer import CustomerProfile
    from app.models.tenant import Tenant

    # Create one identity with two store profiles (own tenant + a seeded other).
    create = await super_admin_client.post(
        "/api/v1/customers/profiles/",
        json={"identity_key": "13800000203", "name": "Shared"},
        headers=AUTH,
    )
    customer_id = create.json()["customer"]["id"]
    other = "tnt-cust-sa"
    db_session.add(Tenant(id=other, name="OtherCust"))
    db_session.add(
        CustomerProfile(
            customer_id=customer_id,
            tenant_id=other,
            status="active",
        )
    )
    await db_session.commit()

    resp = await super_admin_client.get(
        "/api/v1/customers/statistics", headers=AUTH
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # 1 identity (shared across 2 stores).
    assert body["total"] == 1
    assert body["active"] == 1  # has at least one active profile


@pytest.mark.asyncio
async def test_member_can_read_stats(member_client):
    """member has read perms on agents/conversations/customers → 200 on stats."""
    resp = await member_client.get("/api/v1/agents/statistics", headers=AUTH)
    assert resp.status_code == 200
    resp = await member_client.get(
        "/api/v1/conversations/statistics", headers=AUTH
    )
    assert resp.status_code == 200
    resp = await member_client.get("/api/v1/customers/statistics", headers=AUTH)
    assert resp.status_code == 200


# ----------------------------------------------------------- dashboard trends


@pytest.mark.asyncio
async def test_trends_store_scoped(app_client, test_env, db_session):
    """/dashboard/trends returns daily points for this tenant only."""
    from app.models.agent import Conversation
    from app.models.message import Message
    from app.models.tenant import Tenant

    now = datetime.now(UTC)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    # Own tenant: 2 conversations + 3 messages today, 1 yesterday.
    c1 = Conversation(
        tenant_id=test_env.tenant_id,
        agent_id="a1",
        user_id="u1",
        title="t1",
        created_at=today + timedelta(hours=2),
    )
    c2 = Conversation(
        tenant_id=test_env.tenant_id,
        agent_id="a1",
        user_id="u1",
        title="t2",
        created_at=today + timedelta(hours=3),
    )
    c3 = Conversation(
        tenant_id=test_env.tenant_id,
        agent_id="a1",
        user_id="u1",
        title="t3",
        created_at=yesterday + timedelta(hours=1),
    )
    db_session.add_all([c1, c2, c3])
    await db_session.flush()
    # Messages get an explicit created_at so the day-bucket grouping is
    # deterministic (their server_default would stamp them all "now" = today).
    db_session.add_all(
        [
            Message(
                conversation_id=c1.id,
                tenant_id=test_env.tenant_id,
                role="user",
                content="m1",
                created_at=today + timedelta(hours=2),
            ),
            Message(
                conversation_id=c1.id,
                tenant_id=test_env.tenant_id,
                role="assistant",
                content="m2",
                created_at=today + timedelta(hours=2, minutes=5),
            ),
            Message(
                conversation_id=c2.id,
                tenant_id=test_env.tenant_id,
                role="user",
                content="m3",
                created_at=today + timedelta(hours=3),
            ),
            Message(
                conversation_id=c3.id,
                tenant_id=test_env.tenant_id,
                role="user",
                content="m4",
                created_at=yesterday + timedelta(hours=1),
            ),
        ]
    )
    # Other tenant: should NOT appear.
    other = "tnt-trend-other"
    db_session.add(Tenant(id=other, name="OtherTrend"))
    db_session.add(
        Conversation(
            tenant_id=other,
            agent_id="a1",
            user_id="u1",
            title="other",
            created_at=today + timedelta(hours=1),
        )
    )
    await db_session.commit()

    resp = await app_client.get("/api/v1/dashboard/trends?days=7", headers=AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["days"] == 7
    assert len(body["points"]) == 7
    # Points are oldest → newest; last point is today.
    today_iso = today.date().isoformat()
    yesterday_iso = yesterday.date().isoformat()
    by_date = {p["date"]: p for p in body["points"]}
    assert by_date[today_iso]["conversations"] == 2
    assert by_date[today_iso]["messages"] == 3
    assert by_date[yesterday_iso]["conversations"] == 1
    assert by_date[yesterday_iso]["messages"] == 1
    # Other days are zero-filled.
    zeros = [p for p in body["points"] if p["conversations"] == 0 and p["messages"] == 0]
    assert len(zeros) == 5


@pytest.mark.asyncio
async def test_trends_super_admin_cross_tenant(
    super_admin_client, test_env, db_session
):
    """/dashboard/trends as super_admin aggregates across all tenants."""
    from app.models.agent import Conversation
    from app.models.tenant import Tenant

    now = datetime.now(UTC)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    other = "tnt-trend-sa"
    db_session.add(Tenant(id=other, name="OtherTrendSA"))
    # 1 in own tenant, 1 in the other tenant — both today.
    db_session.add(
        Conversation(
            tenant_id=test_env.tenant_id,
            agent_id="a1",
            user_id="u1",
            title="own",
            created_at=today + timedelta(hours=1),
        )
    )
    db_session.add(
        Conversation(
            tenant_id=other,
            agent_id="a1",
            user_id="u1",
            title="other",
            created_at=today + timedelta(hours=2),
        )
    )
    await db_session.commit()

    resp = await super_admin_client.get(
        "/api/v1/dashboard/trends?days=7", headers=AUTH
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    today_iso = today.date().isoformat()
    by_date = {p["date"]: p for p in body["points"]}
    # Cross-tenant: both tenants' conversations today.
    assert by_date[today_iso]["conversations"] == 2


@pytest.mark.asyncio
async def test_trends_days_clamped(app_client):
    """/dashboard/trends clamps days to [1, 90]."""
    # Above the cap → clamped to 90 (200, not 422).
    resp = await app_client.get(
        "/api/v1/dashboard/trends?days=200", headers=AUTH
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["days"] == 90
    # Below the floor → clamped to 1.
    resp = await app_client.get(
        "/api/v1/dashboard/trends?days=0", headers=AUTH
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["days"] == 1


@pytest.mark.asyncio
async def test_trends_default_7_days(app_client):
    """/dashboard/trends defaults to 7 days."""
    resp = await app_client.get("/api/v1/dashboard/trends", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["days"] == 7
    assert len(body["points"]) == 7


# ------------------------------------------------------------- HQ overview


@pytest.mark.asyncio
async def test_overview_super_admin(super_admin_client, test_env, db_session):
    """/dashboard/overview returns platform totals + per-tenant Top N."""
    from app.models.agent import Conversation
    from app.models.tenant import Tenant

    now = datetime.now(UTC)
    other = "tnt-overview-other"
    db_session.add(Tenant(id=other, name="OtherOverview"))
    # Own tenant: 3 recent conversations; other tenant: 1.
    for _ in range(3):
        db_session.add(
            Conversation(
                tenant_id=test_env.tenant_id,
                agent_id="a1",
                user_id="u1",
                title="own",
                created_at=now - timedelta(days=1),
            )
        )
    db_session.add(
        Conversation(
            tenant_id=other,
            agent_id="a1",
            user_id="u1",
            title="other",
            created_at=now - timedelta(days=1),
        )
    )
    await db_session.commit()

    resp = await super_admin_client.get(
        "/api/v1/dashboard/overview", headers=AUTH
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    totals = body["totals"]
    # At least 2 tenants (test_env + other).
    assert totals["tenants"] >= 2
    assert totals["conversations"] == 4  # 3 own + 1 other
    # Top tenants ordered by conversation count desc; own (3) should lead.
    top = body["top_tenants"]
    assert len(top) >= 1
    own_entry = next(t for t in top if t["tenant_id"] == test_env.tenant_id)
    assert own_entry["conversations"] == 3
    other_entry = next(t for t in top if t["tenant_id"] == other)
    assert other_entry["conversations"] == 1


@pytest.mark.asyncio
async def test_overview_forbidden_for_non_super_admin(app_client, member_client):
    """/dashboard/overview is super_admin-only → 403 for tenant users."""
    resp = await app_client.get("/api/v1/dashboard/overview", headers=AUTH)
    assert resp.status_code == 403
    resp = await member_client.get("/api/v1/dashboard/overview", headers=AUTH)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_overview_forbidden_for_hq_staff(hq_staff_client):
    """hq_staff is read-only cross-tenant but NOT super_admin → 403 on overview.

    overview is a platform-admin action (totals + store ranking), gated behind
    require_super_admin; hq_staff must not reach it.
    """
    resp = await hq_staff_client.get("/api/v1/dashboard/overview", headers=AUTH)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_trends_requires_conversations_read_permission(app_client, db_session):
    """/dashboard/trends is guarded by conversations:read (owner has it → 200)."""
    resp = await app_client.get("/api/v1/dashboard/trends?days=7", headers=AUTH)
    assert resp.status_code == 200
