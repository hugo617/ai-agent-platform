"""Conversation-management tests (priority 50).

Covers the search / rename / tags / pin / star / batch-delete surface added on
top of the existing list/read/delete. All seed helpers use the ORM directly
(no real LLM call), mirroring test_customer_conversation.py.

Scope:
- GET / search by title, by message content, by tag
- PATCH title (rename)
- POST / DELETE tags (add + remove)
- PATCH pin / star (toggle)
- POST batch-delete + ownership (can't delete another user's)
- pinned-first ordering
- tenant isolation (other tenant's conversation invisible + unmanageable)
- ConversationRead carries tags / is_pinned / is_starred (defaults [])
"""

import pytest

AUTH = {"Authorization": "Bearer fake"}


# ----------------------------------------------------------- helpers


async def _seed_agent(db_session, tenant_id: str):
    from app.models.agent import Agent

    agent = Agent(name="MgmtBot", tenant_id=tenant_id, system_prompt="hi",
                  model="deepseek-chat")
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)
    return agent


async def _seed_conversation(
    db_session,
    tenant_id: str,
    agent_id: str,
    user_id: str = "test-user",
    *,
    title: str | None = "t",
    tags: list | None = None,
    is_pinned: bool = False,
    is_starred: bool = False,
):
    """Insert a Conversation with the management fields populated."""
    from app.models.agent import Conversation

    conv = Conversation(
        tenant_id=tenant_id,
        agent_id=agent_id,
        user_id=user_id,
        title=title,
        is_pinned=is_pinned,
        is_starred=is_starred,
    )
    # Assign tags after construction so the JSON column picks it up (default
    # list is materialised by the mapper; overwrite for explicit seeds).
    if tags is not None:
        conv.tags = tags
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)
    return conv


async def _seed_message(db_session, tenant_id: str, conv_id: str,
                        content: str, role: str = "user"):
    from app.models.message import Message

    msg = Message(conversation_id=conv_id, tenant_id=tenant_id, role=role,
                  content=content)
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(msg)
    return msg


# ----------------------------------------------------------- model defaults


async def test_new_conversation_has_empty_tags_and_false_flags(db_session, test_env):
    """A conversation created with no tags/pin/star gets the server defaults."""
    agent = await _seed_agent(db_session, test_env.tenant_id)
    conv = await _seed_conversation(
        db_session, test_env.tenant_id, agent.id, user_id=test_env.owner_user,
        title="brand new", tags=None,
    )
    # The column default applies; server_default '[]' backs it for raw rows.
    assert conv.tags == []
    assert conv.is_pinned is False
    assert conv.is_starred is False


# ----------------------------------------------------------- ConversationRead


@pytest.mark.asyncio
async def test_list_returns_management_fields(app_client, db_session, test_env):
    """ConversationRead includes tags / is_pinned / is_starred with defaults."""
    agent = await _seed_agent(db_session, test_env.tenant_id)
    await _seed_conversation(
        db_session, test_env.tenant_id, agent.id,
        user_id=test_env.owner_user, title="plain",
    )
    resp = await app_client.get("/api/v1/conversations/", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["tags"] == []
    assert body[0]["is_pinned"] is False
    assert body[0]["is_starred"] is False


# ----------------------------------------------------------- search


@pytest.mark.asyncio
async def test_search_by_title(app_client, db_session, test_env):
    """search matches the conversation title (case-insensitive substring)."""
    agent = await _seed_agent(db_session, test_env.tenant_id)
    await _seed_conversation(
        db_session, test_env.tenant_id, agent.id,
        user_id=test_env.owner_user, title="Project Alpha",
    )
    await _seed_conversation(
        db_session, test_env.tenant_id, agent.id,
        user_id=test_env.owner_user, title="Random notes",
    )
    resp = await app_client.get(
        "/api/v1/conversations/?search=project", headers=AUTH
    )
    assert resp.status_code == 200
    titles = [c["title"] for c in resp.json()]
    assert titles == ["Project Alpha"]


@pytest.mark.asyncio
async def test_search_by_message_content(app_client, db_session, test_env):
    """search matches any message content, not just the title."""
    agent = await _seed_agent(db_session, test_env.tenant_id)
    # A conversation whose title does NOT contain the term…
    conv = await _seed_conversation(
        db_session, test_env.tenant_id, agent.id,
        user_id=test_env.owner_user, title="untitled",
    )
    # …but one of its messages does.
    await _seed_message(
        db_session, test_env.tenant_id, conv.id,
        content="let us discuss the QUANTUM physics here",
    )
    resp = await app_client.get(
        "/api/v1/conversations/?search=quantum", headers=AUTH
    )
    assert resp.status_code == 200
    ids = [c["id"] for c in resp.json()]
    assert ids == [conv.id]


@pytest.mark.asyncio
async def test_search_no_match_returns_empty(app_client, db_session, test_env):
    agent = await _seed_agent(db_session, test_env.tenant_id)
    await _seed_conversation(
        db_session, test_env.tenant_id, agent.id,
        user_id=test_env.owner_user, title="hello",
    )
    resp = await app_client.get(
        "/api/v1/conversations/?search=zzznomatch", headers=AUTH
    )
    assert resp.status_code == 200
    assert resp.json() == []


# ----------------------------------------------------------- tag filter


@pytest.mark.asyncio
async def test_filter_by_tag(app_client, db_session, test_env):
    """tag filters to conversations whose tags array contains it."""
    agent = await _seed_agent(db_session, test_env.tenant_id)
    vip = await _seed_conversation(
        db_session, test_env.tenant_id, agent.id,
        user_id=test_env.owner_user, title="vip one", tags=["vip", "work"],
    )
    await _seed_conversation(
        db_session, test_env.tenant_id, agent.id,
        user_id=test_env.owner_user, title="plain one", tags=["work"],
    )
    resp = await app_client.get(
        "/api/v1/conversations/?tag=vip", headers=AUTH
    )
    assert resp.status_code == 200
    ids = [c["id"] for c in resp.json()]
    assert ids == [vip.id]


@pytest.mark.asyncio
async def test_search_and_tag_combined(app_client, db_session, test_env):
    """search + tag compose (both filters must hold)."""
    agent = await _seed_agent(db_session, test_env.tenant_id)
    a = await _seed_conversation(
        db_session, test_env.tenant_id, agent.id,
        user_id=test_env.owner_user, title="alpha matching", tags=["vip"],
    )
    await _seed_conversation(
        db_session, test_env.tenant_id, agent.id,
        user_id=test_env.owner_user, title="alpha no-tag", tags=[],
    )
    resp = await app_client.get(
        "/api/v1/conversations/?search=alpha&tag=vip", headers=AUTH
    )
    assert resp.status_code == 200
    ids = [c["id"] for c in resp.json()]
    assert ids == [a.id]


# ----------------------------------------------------------- ordering


@pytest.mark.asyncio
async def test_pinned_first_ordering(app_client, db_session, test_env):
    """Pinned conversations sort above non-pinned regardless of recency."""
    agent = await _seed_agent(db_session, test_env.tenant_id)
    # Seed a non-pinned first (older updated_at), then a pinned one.
    await _seed_conversation(
        db_session, test_env.tenant_id, agent.id,
        user_id=test_env.owner_user, title="not pinned",
    )
    pinned = await _seed_conversation(
        db_session, test_env.tenant_id, agent.id,
        user_id=test_env.owner_user, title="pinned", is_pinned=True,
    )
    resp = await app_client.get("/api/v1/conversations/", headers=AUTH)
    ids = [c["id"] for c in resp.json()]
    # Pinned bubbles to the top even though it was inserted later.
    assert ids[0] == pinned.id


# ----------------------------------------------------------- rename


@pytest.mark.asyncio
async def test_rename_conversation(app_client, db_session, test_env):
    agent = await _seed_agent(db_session, test_env.tenant_id)
    conv = await _seed_conversation(
        db_session, test_env.tenant_id, agent.id,
        user_id=test_env.owner_user, title="old title",
    )
    resp = await app_client.patch(
        f"/api/v1/conversations/{conv.id}/title",
        json={"title": "new title"}, headers=AUTH,
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "new title"


@pytest.mark.asyncio
async def test_rename_other_users_conversation_404(app_client, db_session, test_env):
    """Renaming a conversation owned by a different user → 404 (no leak)."""
    agent = await _seed_agent(db_session, test_env.tenant_id)
    conv = await _seed_conversation(
        db_session, test_env.tenant_id, agent.id,
        user_id="someone-else", title="not yours",
    )
    resp = await app_client.patch(
        f"/api/v1/conversations/{conv.id}/title",
        json={"title": "hijacked"}, headers=AUTH,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_rename_nonexistent_404(app_client):
    resp = await app_client.patch(
        "/api/v1/conversations/no-such-id/title",
        json={"title": "x"}, headers=AUTH,
    )
    assert resp.status_code == 404


# ----------------------------------------------------------- tags add/remove


@pytest.mark.asyncio
async def test_add_and_remove_tag(app_client, db_session, test_env):
    agent = await _seed_agent(db_session, test_env.tenant_id)
    conv = await _seed_conversation(
        db_session, test_env.tenant_id, agent.id,
        user_id=test_env.owner_user, title="tag me", tags=[],
    )
    # Add
    resp = await app_client.post(
        f"/api/v1/conversations/{conv.id}/tags",
        json={"tag": "important"}, headers=AUTH,
    )
    assert resp.status_code == 200
    assert resp.json()["tags"] == ["important"]

    # Add a second tag
    resp = await app_client.post(
        f"/api/v1/conversations/{conv.id}/tags",
        json={"tag": "followup"}, headers=AUTH,
    )
    assert resp.json()["tags"] == ["important", "followup"]

    # Adding a duplicate is idempotent.
    resp = await app_client.post(
        f"/api/v1/conversations/{conv.id}/tags",
        json={"tag": "important"}, headers=AUTH,
    )
    assert resp.json()["tags"] == ["important", "followup"]

    # Remove one
    resp = await app_client.delete(
        f"/api/v1/conversations/{conv.id}/tags/important", headers=AUTH,
    )
    assert resp.status_code == 200
    assert resp.json()["tags"] == ["followup"]


@pytest.mark.asyncio
async def test_add_tag_other_user_404(app_client, db_session, test_env):
    agent = await _seed_agent(db_session, test_env.tenant_id)
    conv = await _seed_conversation(
        db_session, test_env.tenant_id, agent.id,
        user_id="someone-else", title="not yours",
    )
    resp = await app_client.post(
        f"/api/v1/conversations/{conv.id}/tags",
        json={"tag": "x"}, headers=AUTH,
    )
    assert resp.status_code == 404


# ----------------------------------------------------------- pin / star


@pytest.mark.asyncio
async def test_pin_and_unpin(app_client, db_session, test_env):
    agent = await _seed_agent(db_session, test_env.tenant_id)
    conv = await _seed_conversation(
        db_session, test_env.tenant_id, agent.id,
        user_id=test_env.owner_user, title="pin me",
    )
    resp = await app_client.patch(
        f"/api/v1/conversations/{conv.id}/pin",
        json={"pinned": True}, headers=AUTH,
    )
    assert resp.status_code == 200
    assert resp.json()["is_pinned"] is True

    resp = await app_client.patch(
        f"/api/v1/conversations/{conv.id}/pin",
        json={"pinned": False}, headers=AUTH,
    )
    assert resp.json()["is_pinned"] is False


@pytest.mark.asyncio
async def test_star_and_unstar(app_client, db_session, test_env):
    agent = await _seed_agent(db_session, test_env.tenant_id)
    conv = await _seed_conversation(
        db_session, test_env.tenant_id, agent.id,
        user_id=test_env.owner_user, title="star me",
    )
    resp = await app_client.patch(
        f"/api/v1/conversations/{conv.id}/star",
        json={"starred": True}, headers=AUTH,
    )
    assert resp.status_code == 200
    assert resp.json()["is_starred"] is True

    resp = await app_client.patch(
        f"/api/v1/conversations/{conv.id}/star",
        json={"starred": False}, headers=AUTH,
    )
    assert resp.json()["is_starred"] is False


@pytest.mark.asyncio
async def test_pin_other_user_404(app_client, db_session, test_env):
    agent = await _seed_agent(db_session, test_env.tenant_id)
    conv = await _seed_conversation(
        db_session, test_env.tenant_id, agent.id,
        user_id="someone-else", title="not yours",
    )
    resp = await app_client.patch(
        f"/api/v1/conversations/{conv.id}/pin",
        json={"pinned": True}, headers=AUTH,
    )
    assert resp.status_code == 404


# ----------------------------------------------------------- batch delete


@pytest.mark.asyncio
async def test_batch_delete_own_conversations(app_client, db_session, test_env):
    agent = await _seed_agent(db_session, test_env.tenant_id)
    c1 = await _seed_conversation(
        db_session, test_env.tenant_id, agent.id,
        user_id=test_env.owner_user, title="c1",
    )
    c2 = await _seed_conversation(
        db_session, test_env.tenant_id, agent.id,
        user_id=test_env.owner_user, title="c2",
    )
    resp = await app_client.post(
        "/api/v1/conversations/batch-delete",
        json={"conversation_ids": [c1.id, c2.id]}, headers=AUTH,
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 2

    # Both are gone from the list.
    resp = await app_client.get("/api/v1/conversations/", headers=AUTH)
    ids = [c["id"] for c in resp.json()]
    assert c1.id not in ids
    assert c2.id not in ids


@pytest.mark.asyncio
async def test_batch_delete_rejects_other_users_conversation(
    app_client, db_session, test_env
):
    """A foreign id in the batch → 404 (nothing deleted, ownership enforced)."""
    agent = await _seed_agent(db_session, test_env.tenant_id)
    mine = await _seed_conversation(
        db_session, test_env.tenant_id, agent.id,
        user_id=test_env.owner_user, title="mine",
    )
    theirs = await _seed_conversation(
        db_session, test_env.tenant_id, agent.id,
        user_id="someone-else", title="theirs",
    )
    resp = await app_client.post(
        "/api/v1/conversations/batch-delete",
        json={"conversation_ids": [mine.id, theirs.id]}, headers=AUTH,
    )
    # The foreign id yields 404 and the transaction is not committed, so the
    # caller's own conversation survives too.
    assert resp.status_code == 404
    resp = await app_client.get("/api/v1/conversations/", headers=AUTH)
    ids = [c["id"] for c in resp.json()]
    assert mine.id in ids  # not deleted (validation failed first)


@pytest.mark.asyncio
async def test_batch_delete_empty_list_rejected(app_client):
    """An empty id list is rejected by the schema (min_length=1) → 422."""
    resp = await app_client.post(
        "/api/v1/conversations/batch-delete",
        json={"conversation_ids": []}, headers=AUTH,
    )
    assert resp.status_code == 422


# ----------------------------------------------------------- tenant isolation


@pytest.mark.asyncio
async def test_other_tenant_conversation_invisible_and_unmanageable(
    app_client, db_session
):
    """A conversation in another tenant is invisible and cannot be mutated."""
    from app.models.agent import Conversation

    other = Conversation(
        id="conv-other-tenant-mgmt",
        tenant_id="tnt-fully-isolated",
        agent_id="some-agent",
        user_id="other-user",
        title="Secret Other Tenant",
    )
    db_session.add(other)
    await db_session.commit()

    # Not in this tenant's list.
    resp = await app_client.get("/api/v1/conversations/", headers=AUTH)
    assert all(c["id"] != other.id for c in resp.json())

    # Cannot rename / pin / tag / delete it (all 404 — no existence leak).
    assert (
        await app_client.patch(
            f"/api/v1/conversations/{other.id}/title",
            json={"title": "x"}, headers=AUTH,
        )
    ).status_code == 404
    assert (
        await app_client.patch(
            f"/api/v1/conversations/{other.id}/pin",
            json={"pinned": True}, headers=AUTH,
        )
    ).status_code == 404
    assert (
        await app_client.post(
            f"/api/v1/conversations/{other.id}/tags",
            json={"tag": "x"}, headers=AUTH,
        )
    ).status_code == 404
    assert (
        await app_client.post(
            "/api/v1/conversations/batch-delete",
            json={"conversation_ids": [other.id]}, headers=AUTH,
        )
    ).status_code == 404


# ----------------------------------------------------------- permission guard


@pytest.mark.asyncio
async def test_member_cannot_rename_conversation(member_client, db_session, test_env):
    """member lacks conversations:update → 403 (guard fires before lookup).

    The member role in the test casbin seed holds conversations:read/create/chat
    but NOT update, so the management mutations are 403 for them.
    """
    agent = await _seed_agent(db_session, test_env.tenant_id)
    conv = await _seed_conversation(
        db_session, test_env.tenant_id, agent.id,
        user_id=test_env.owner_user, title="x",
    )
    resp = await member_client.patch(
        f"/api/v1/conversations/{conv.id}/title",
        json={"title": "y"}, headers=AUTH,
    )
    assert resp.status_code == 403
