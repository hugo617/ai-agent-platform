"""Global cross-entity search tests (priority 51).

Covers:
- GET /search?q= hits each entity type (agent name, customer name, conversation
  title) and groups them by category.
- Permission split: store users search their own tenant; super_admin / hq_staff
  additionally get users + tenants sections and see across every tenant.
- Tenant isolation: a store user never sees another tenant's agent/profile.
- Short query guard: q shorter than 2 chars returns an empty result (no hits).
- limit_per_type bounds each section.
- per-entity search params added on agents/customers list endpoints.
"""

import uuid

import pytest

AUTH = {"Authorization": "Bearer fake"}


# ----------------------------------------------------------- helpers


async def _seed_agent(db_session, tenant_id: str, *, name: str):
    from app.models.agent import Agent

    agent = Agent(name=name, tenant_id=tenant_id, system_prompt="", model="deepseek-chat")
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)
    return agent


async def _seed_customer_profile(
    db_session, tenant_id: str, *, identity_key: str, name: str
):
    """Build a Customer + this-tenant Profile directly (bypasses the service)."""
    from app.models.customer import Customer, CustomerProfile

    customer = Customer(identity_key=identity_key, name=name)
    db_session.add(customer)
    await db_session.flush()
    profile = CustomerProfile(
        customer_id=customer.id, tenant_id=tenant_id, status="active"
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(customer)
    await db_session.refresh(profile)
    return customer, profile


async def _seed_conversation(
    db_session, tenant_id: str, agent_id: str, user_id: str, *, title: str
):
    from app.models.agent import Conversation

    conv = Conversation(
        tenant_id=tenant_id, agent_id=agent_id, user_id=user_id, title=title
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)
    return conv


async def _seed_tenant(db_session, *, name: str) -> str:
    from app.models.tenant import Tenant

    tid = f"tnt-{uuid.uuid4().hex}"
    db_session.add(Tenant(id=tid, name=name))
    await db_session.commit()
    return tid


# ----------------------------------------------------------- per-entity search params


@pytest.mark.asyncio
async def test_agents_list_supports_search(app_client, db_session, test_env):
    """GET /agents/?search= narrows by name (ILIKE), tenant-scoped."""
    await _seed_agent(db_session, test_env.tenant_id, name="Sales Bot")
    await _seed_agent(db_session, test_env.tenant_id, name="Support Bot")
    await _seed_agent(db_session, test_env.tenant_id, name="Finance Agent")

    resp = await app_client.get("/api/v1/agents/?search=sales", headers=AUTH)
    assert resp.status_code == 200, resp.text
    names = {a["name"] for a in resp.json()}
    assert names == {"Sales Bot"}


@pytest.mark.asyncio
async def test_agents_list_search_empty_returns_all(app_client, db_session, test_env):
    """An empty/absent search returns every tenant agent (no filter)."""
    await _seed_agent(db_session, test_env.tenant_id, name="Alpha")
    await _seed_agent(db_session, test_env.tenant_id, name="Beta")

    resp = await app_client.get("/api/v1/agents/?search=", headers=AUTH)
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


@pytest.mark.asyncio
async def test_customer_profiles_list_supports_search(
    app_client, db_session, test_env
):
    """GET /customers/profiles/?search= matches name OR identity_key."""
    await _seed_customer_profile(
        db_session, test_env.tenant_id, identity_key="13800000001", name="Carol Danvers"
    )
    await _seed_customer_profile(
        db_session, test_env.tenant_id, identity_key="13800000002", name="Diana Prince"
    )

    # search by name fragment
    resp = await app_client.get(
        "/api/v1/customers/profiles/",
        params={"search": "carol"},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 1
    assert resp.json()[0]["customer"]["name"] == "Carol Danvers"

    # search by identity_key fragment
    resp = await app_client.get(
        "/api/v1/customers/profiles/",
        params={"search": "13800000002"},
        headers=AUTH,
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["customer"]["name"] == "Diana Prince"


# ----------------------------------------------------------- global search: hits


@pytest.mark.asyncio
async def test_global_search_agent_hit(app_client, db_session, test_env):
    """A store user finds their agent via the global search."""
    await _seed_agent(db_session, test_env.tenant_id, name="GlobalFinder")
    resp = await app_client.get(
        "/api/v1/search?q=finder", headers=AUTH
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["agents"]) == 1
    assert body["agents"][0]["label"] == "GlobalFinder"
    assert body["agents"][0]["type"] == "agent"
    # store user has no users/tenants sections populated
    assert body["users"] == []
    assert body["tenants"] == []


@pytest.mark.asyncio
async def test_global_search_customer_hit(app_client, db_session, test_env):
    """A store user finds their customer profile by name."""
    await _seed_customer_profile(
        db_session, test_env.tenant_id, identity_key="13900000001", name="Alice Wong"
    )
    resp = await app_client.get(
        "/api/v1/search", params={"q": "alice"}, headers=AUTH
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["customers"]) == 1
    assert body["customers"][0]["label"] == "Alice Wong"
    assert body["customers"][0]["type"] == "customer"


@pytest.mark.asyncio
async def test_global_search_customer_hit_by_identity(app_client, db_session, test_env):
    """A store user finds a customer by identity_key fragment."""
    await _seed_customer_profile(
        db_session, test_env.tenant_id, identity_key="13700001234", name="赵六"
    )
    resp = await app_client.get("/api/v1/search?q=1370000", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["customers"]) == 1
    assert body["customers"][0]["label"] == "赵六"


@pytest.mark.asyncio
async def test_global_search_conversation_hit(app_client, db_session, test_env):
    """A store user finds their conversation by title."""
    agent = await _seed_agent(db_session, test_env.tenant_id, name="ChatHost")
    await _seed_conversation(
        db_session,
        test_env.tenant_id,
        agent.id,
        user_id=test_env.owner_user,
        title="Quarterly review planning",
    )
    resp = await app_client.get("/api/v1/search?q=quarterly", headers=AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["conversations"]) == 1
    assert body["conversations"][0]["label"] == "Quarterly review planning"
    assert body["conversations"][0]["type"] == "conversation"


@pytest.mark.asyncio
async def test_global_search_returns_all_categories(app_client, db_session, test_env):
    """One query that matches an agent + customer + conversation returns hits
    in each respective category, grouped correctly."""
    agent = await _seed_agent(db_session, test_env.tenant_id, name="Acme Bot")
    await _seed_customer_profile(
        db_session, test_env.tenant_id, identity_key="13000000001", name="Acme Corp"
    )
    await _seed_conversation(
        db_session,
        test_env.tenant_id,
        agent.id,
        user_id=test_env.owner_user,
        title="Acme onboarding chat",
    )
    resp = await app_client.get("/api/v1/search?q=acme", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["agents"]) == 1
    assert len(body["customers"]) == 1
    assert len(body["conversations"]) == 1


# ----------------------------------------------------------- global search: guard


@pytest.mark.asyncio
async def test_global_search_short_query_returns_empty(app_client, db_session, test_env):
    """A query shorter than 2 chars returns an empty result without erroring."""
    await _seed_agent(db_session, test_env.tenant_id, name="AA")
    resp = await app_client.get("/api/v1/search?q=a", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["agents"] == []
    assert body["customers"] == []
    assert body["conversations"] == []


@pytest.mark.asyncio
async def test_global_search_blank_query_returns_empty(app_client):
    """A whitespace-only query is treated as empty."""
    resp = await app_client.get("/api/v1/search?q=%20%20", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["agents"] == []


# ----------------------------------------------------------- tenant isolation


@pytest.mark.asyncio
async def test_store_user_search_is_tenant_scoped(
    app_client, db_session, test_env
):
    """A store user never sees another tenant's agents in the global search."""
    # own tenant
    await _seed_agent(db_session, test_env.tenant_id, name="Visible Agent")
    # other tenant
    other_tenant = await _seed_tenant(db_session, name="Other Store")
    await _seed_agent(db_session, other_tenant, name="Hidden Agent")

    resp = await app_client.get("/api/v1/search?q=agent", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    labels = {a["label"] for a in body["agents"]}
    assert "Visible Agent" in labels
    assert "Hidden Agent" not in labels


@pytest.mark.asyncio
async def test_store_user_customer_search_is_tenant_scoped(
    app_client, db_session, test_env
):
    """A store user's customer search stays within their tenant's profiles."""
    await _seed_customer_profile(
        db_session, test_env.tenant_id, identity_key="13100000001", name="Tenant Customer"
    )
    other_tenant = await _seed_tenant(db_session, name="Other Store 2")
    await _seed_customer_profile(
        db_session, other_tenant, identity_key="13100000002", name="Other Customer"
    )

    resp = await app_client.get("/api/v1/search?q=customer", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    labels = {c["label"] for c in body["customers"]}
    assert "Tenant Customer" in labels
    assert "Other Customer" not in labels


# ----------------------------------------------------------- super_admin scope


@pytest.mark.asyncio
async def test_super_admin_search_adds_users_and_tenants(
    super_admin_client, db_session, test_env
):
    """super_admin gets the users + tenants sections populated on a match."""
    from app.models.tenant import User

    # Seed a user whose username matches, plus a tenant whose name matches.
    async with test_env.factory() as session:
        session.add(
            User(
                id=f"u-{uuid.uuid4().hex}",
                username="adminfind",
                email="adminfind@example.com",
                status="active",
            )
        )
        await session.commit()

    await _seed_tenant(db_session, name="Findable Store")

    resp = await super_admin_client.get("/api/v1/search?q=find", headers=AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # super_admin sees cross-tenant: users + tenants sections are populated.
    assert any("adminfind" in (u["label"] or "") for u in body["users"])
    assert any("Findable Store" == t["label"] for t in body["tenants"])


@pytest.mark.asyncio
async def test_super_admin_search_cross_tenant_agents(
    super_admin_client, db_session, test_env
):
    """super_admin sees agents from every tenant in the global search."""
    await _seed_agent(db_session, test_env.tenant_id, name="HQ Visible Agent")
    other_tenant = await _seed_tenant(db_session, name="HQ Other Store")
    await _seed_agent(db_session, other_tenant, name="HQ Other Agent")

    resp = await super_admin_client.get("/api/v1/search?q=hq", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    labels = {a["label"] for a in body["agents"]}
    assert "HQ Visible Agent" in labels
    assert "HQ Other Agent" in labels


@pytest.mark.asyncio
async def test_super_admin_search_cross_tenant_customers(
    super_admin_client, db_session, test_env
):
    """super_admin searches the global Customer table (name/identity_key)."""
    await _seed_customer_profile(
        db_session, test_env.tenant_id, identity_key="13200000001", name="Global Customer"
    )
    other_tenant = await _seed_tenant(db_session, name="HQ Customer Store")
    await _seed_customer_profile(
        db_session, other_tenant, identity_key="13200000002", name="Other Global Customer"
    )

    resp = await super_admin_client.get("/api/v1/search?q=global", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    labels = {c["label"] for c in body["customers"]}
    assert "Global Customer" in labels
    assert "Other Global Customer" in labels


@pytest.mark.asyncio
async def test_hq_staff_search_adds_users_and_tenants(
    hq_staff_client, db_session, test_env
):
    """hq_staff is also a cross-tenant viewer → users + tenants appear."""
    await _seed_tenant(db_session, name="HQ Staff Findable Store")

    resp = await hq_staff_client.get(
        "/api/v1/search?q=findable", headers=AUTH
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert any("Findable" in (t["label"] or "") for t in body["tenants"])


# ----------------------------------------------------------- limit_per_type


@pytest.mark.asyncio
async def test_limit_per_type_bounds_section(app_client, db_session, test_env):
    """limit_per_type caps how many hits each category returns."""
    for i in range(4):
        await _seed_agent(db_session, test_env.tenant_id, name=f"Bounded Agent {i}")
    resp = await app_client.get(
        "/api/v1/search?q=bounded&limit_per_type=2", headers=AUTH
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["agents"]) == 2


@pytest.mark.asyncio
async def test_limit_per_type_default_is_five(app_client, db_session, test_env):
    """The default limit_per_type is 5."""
    for i in range(7):
        await _seed_agent(db_session, test_env.tenant_id, name=f"Default Lim {i}")
    resp = await app_client.get("/api/v1/search?q=default%20lim", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["agents"]) == 5


# ----------------------------------------------------------- DTO shape


@pytest.mark.asyncio
async def test_search_result_dto_shape(app_client, db_session, test_env):
    """Each hit carries id + label + type (the dropdown contract)."""
    agent = await _seed_agent(db_session, test_env.tenant_id, name="Shape Bot")
    resp = await app_client.get("/api/v1/search?q=shape", headers=AUTH)
    assert resp.status_code == 200
    item = resp.json()["agents"][0]
    assert set(item.keys()) == {"id", "label", "type"}
    assert item["id"] == agent.id


@pytest.mark.asyncio
async def test_search_missing_q_returns_empty(app_client):
    """No q param at all → empty result (the default is '')."""
    resp = await app_client.get("/api/v1/search", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["agents"] == []
    assert body["customers"] == []
    assert body["conversations"] == []
