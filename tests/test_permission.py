"""Multi-tenant permission isolation tests.

The single most important property of the platform: a user in tenant A can
never see or touch resources in tenant B.
"""

import pytest


@pytest.mark.asyncio
async def test_owner_can_read_agents(app_client):
    """Owner has read permission by default (seeded)."""
    resp = await app_client.get(
        "/api/v1/agents/", headers={"Authorization": "Bearer fake"}
    )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_cross_tenant_agent_is_invisible(app_client, db_session, tenant_owner):
    """An agent created directly in tenant B must be invisible to tenant A's user."""
    from app.models.agent import Agent

    other_tenant = "tnt-OTHER"
    other_agent = Agent(
        tenant_id=other_tenant, name="leaked-agent", model="gpt-4o-mini"
    )
    db_session.add(other_agent)
    await db_session.commit()

    # Tenant A owner tries to GET the other tenant's agent by id.
    resp = await app_client.get(
        f"/api/v1/agents/{other_agent.id}",
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 404  # not 200 — isolation enforced


@pytest.mark.asyncio
async def test_permission_denied_without_policy(app_client, db_session, tenant_owner):
    """A user with NO role in casbin is denied even within a tenant they can read."""
    from app.core import casbin_enforcer as casbin_mod

    # Strip ALL roles the user holds in this tenant.
    e = casbin_mod.get_enforcer()
    e.delete_roles_for_user_in_domain(
        tenant_owner["user_id"], "owner", tenant_owner["tenant_id"]
    )

    resp = await app_client.get(
        "/api/v1/agents/", headers={"Authorization": "Bearer fake"}
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_member_cannot_delete_agent(app_client, db_session, tenant_owner):
    """The 'member' role lacks 'agents/delete' so the endpoint must 403."""
    from app.core import casbin_enforcer as casbin_mod

    # Swap owner -> member: drop the owner role in the domain, then add 'member'.
    e = casbin_mod.get_enforcer()
    e.delete_roles_for_user_in_domain(
        tenant_owner["user_id"], "owner", tenant_owner["tenant_id"]
    )
    e.add_role_for_user_in_domain(
        tenant_owner["user_id"], "member", tenant_owner["tenant_id"]
    )

    # First create an agent as owner is impossible now, so insert directly.
    from app.models.agent import Agent

    agent = Agent(
        tenant_id=tenant_owner["tenant_id"], name="a", model="gpt-4o-mini"
    )
    db_session.add(agent)
    await db_session.commit()

    resp = await app_client.delete(
        f"/api/v1/agents/{agent.id}", headers={"Authorization": "Bearer fake"}
    )
    assert resp.status_code == 403
