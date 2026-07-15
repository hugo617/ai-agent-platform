"""CSV export endpoint tests — ``GET /exports/{entity}``.

Covers the four entities (customers / conversations / usage / logs) plus the
shared behaviour:

- CSV shape: UTF-8 BOM + header row + data rows parse with ``csv``.
- Store scope: owner exports only their tenant's rows.
- Multi-tenant isolation: store A's export cannot include store B's rows.
- Cross-tenant: super_admin sees rows across all tenants.
- Permission: a role without the entity's read perm gets 403.
- Date range: ``date_from`` / ``date_to`` filter rows.
- Streaming: the body parses end-to-end as CSV with the expected row count
  (the streaming generator yields chunks; the test joins them).
- Bad inputs: unknown entity → 404; malformed date → 400.

Seed helpers mirror ``test_logs_api.py`` (direct inserts, deterministic
timestamps) so the assertions don't depend on LoggingService / chat flow.
"""

import csv
import io
from datetime import UTC, datetime, timedelta

import pytest

AUTH = {"Authorization": "Bearer fake"}


def _parse_csv(body: bytes) -> list[list[str]]:
    """Decode + strip the UTF-8 BOM + parse the CSV body into rows.

    The BOM (``\\ufeff``) is the first char of the streamed body; if we don't
    strip it, ``csv.reader`` attaches it to the first header name
    (``"\\ufeffname"``) and header assertions break. Mirrors what Excel does
    on open (consume the BOM, then parse).
    """
    text = body.decode("utf-8-sig")  # utf-8-sig transparently drops the BOM
    return list(csv.reader(io.StringIO(text)))


# ----------------------------------------------------- seed helpers


async def _seed_customer(db_session, *, tenant_id, identity_key, name, status="active", tags=None, gender="male"):
    """Insert a Customer + CustomerProfile in one tenant and commit."""
    from app.models.customer import Customer, CustomerProfile

    c = Customer(identity_key=identity_key, name=name, gender=gender)
    db_session.add(c)
    await db_session.flush()
    db_session.add(
        CustomerProfile(
            customer_id=c.id,
            tenant_id=tenant_id,
            status=status,
            tags=tags or {},
        )
    )
    await db_session.commit()
    return c


async def _seed_conversation(
    db_session,
    *,
    tenant_id,
    agent_id,
    user_id,
    title,
    created_at=None,
    message_count=0,
):
    """Insert a Conversation (and N blank Messages) in one tenant."""
    from app.models.agent import Conversation
    from app.models.message import Message

    conv = Conversation(
        tenant_id=tenant_id,
        agent_id=agent_id,
        user_id=user_id,
        title=title,
        created_at=created_at or datetime.now(UTC),
    )
    db_session.add(conv)
    await db_session.flush()
    for _ in range(message_count):
        db_session.add(
            Message(
                conversation_id=conv.id,
                tenant_id=tenant_id,
                role="user",
                content="x",
            )
        )
    await db_session.commit()
    return conv


async def _seed_usage(
    db_session,
    *,
    tenant_id,
    conversation_id,
    user_id,
    model="gpt-4o",
    prompt=10,
    completion=5,
    total=15,
    customer_id=None,
    created_at=None,
):
    from app.models.usage_event import UsageEvent

    db_session.add(
        UsageEvent(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            user_id=user_id,
            message_id=f"msg-{tenant_id}-{datetime.now(UTC).timestamp()}",
            model=model,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            customer_id=customer_id,
            created_at=created_at or datetime.now(UTC),
        )
    )
    await db_session.commit()


async def _seed_log(db_session, *, tenant_id, action="create", message="did x", created_at=None):
    from app.models.log import SystemLog

    db_session.add(
        SystemLog(
            level="info",
            action=action,
            module="users",
            message=message,
            tenant_id=tenant_id,
            created_at=created_at or datetime.now(UTC),
        )
    )
    await db_session.commit()


# A shared agent id. The conversations export joins messages by conversation_id,
# so we only need the agent_id column to be non-null on the rows we read.
_AGENT_ID = "agent-export-test-0000000000000000"


# ============================================================ customers


@pytest.mark.asyncio
async def test_export_customers_store_scope(app_client, db_session, test_env):
    """Store owner exports their tenant's customer profiles as CSV."""
    await _seed_customer(
        db_session, tenant_id=test_env.tenant_id, identity_key="13800000001", name="张三"
    )
    await _seed_customer(
        db_session, tenant_id=test_env.tenant_id, identity_key="13800000002", name="李四"
    )

    resp = await app_client.get("/api/v1/exports/customers", headers=AUTH)
    assert resp.status_code == 200, resp.text
    rows = _parse_csv(resp.content)
    # header + 2 data rows
    assert rows[0] == ["name", "identity_key", "gender", "status", "created_at", "tags"]
    assert len(rows) == 3
    names = {r[0] for r in rows[1:]}
    assert names == {"张三", "李四"}


@pytest.mark.asyncio
async def test_export_customers_tenant_isolation(app_client, db_session, test_env):
    """A store's export cannot include another tenant's customers."""
    other = "tnt-export-cust-other"
    await _seed_customer(
        db_session, tenant_id=test_env.tenant_id, identity_key="13800000001", name="本店客户"
    )
    await _seed_customer(
        db_session, tenant_id=other, identity_key="13900000002", name="他店客户"
    )

    resp = await app_client.get("/api/v1/exports/customers", headers=AUTH)
    assert resp.status_code == 200
    rows = _parse_csv(resp.content)
    # only own tenant: 1 data row
    assert len(rows) == 2
    assert rows[1][0] == "本店客户"


@pytest.mark.asyncio
async def test_export_customers_super_admin_cross_tenant(
    super_admin_client, db_session, test_env
):
    """super_admin export spans every tenant."""
    other = "tnt-export-cust-sa"
    await _seed_customer(
        db_session, tenant_id=test_env.tenant_id, identity_key="13800000001", name="本店"
    )
    await _seed_customer(
        db_session, tenant_id=other, identity_key="13900000002", name="他店"
    )

    resp = await super_admin_client.get("/api/v1/exports/customers", headers=AUTH)
    assert resp.status_code == 200
    rows = _parse_csv(resp.content)
    # 2 tenants × 1 customer = 2 data rows
    assert len(rows) == 3
    assert {r[0] for r in rows[1:]} == {"本店", "他店"}


# ============================================================ conversations


@pytest.mark.asyncio
async def test_export_conversations_store_scope(app_client, db_session, test_env):
    """Store owner exports their own conversations with message_count."""
    await _seed_conversation(
        db_session,
        tenant_id=test_env.tenant_id,
        agent_id=_AGENT_ID,
        user_id=test_env.owner_user,
        title="对话 A",
        message_count=3,
    )
    await _seed_conversation(
        db_session,
        tenant_id=test_env.tenant_id,
        agent_id=_AGENT_ID,
        user_id=test_env.owner_user,
        title="对话 B",
        message_count=1,
    )

    resp = await app_client.get("/api/v1/exports/conversations", headers=AUTH)
    assert resp.status_code == 200, resp.text
    rows = _parse_csv(resp.content)
    assert rows[0] == [
        "title",
        "agent_id",
        "user_id",
        "created_at",
        "message_count",
        "is_pinned",
        "is_starred",
    ]
    assert len(rows) == 3
    # message_count is computed per conversation
    titles = {r[0]: r[4] for r in rows[1:]}
    assert titles == {"对话 A": "3", "对话 B": "1"}


@pytest.mark.asyncio
async def test_export_conversations_super_admin_cross_tenant(
    super_admin_client, db_session, test_env
):
    """super_admin export spans every tenant's conversations."""
    other = "tnt-export-conv-sa"
    await _seed_conversation(
        db_session,
        tenant_id=test_env.tenant_id,
        agent_id=_AGENT_ID,
        user_id=test_env.owner_user,
        title="本店对话",
    )
    await _seed_conversation(
        db_session,
        tenant_id=other,
        agent_id=_AGENT_ID,
        user_id="cross-user",
        title="他店对话",
    )

    resp = await super_admin_client.get("/api/v1/exports/conversations", headers=AUTH)
    assert resp.status_code == 200
    rows = _parse_csv(resp.content)
    assert len(rows) == 3  # header + 2
    assert {r[0] for r in rows[1:]} == {"本店对话", "他店对话"}


@pytest.mark.asyncio
async def test_export_conversations_super_admin_null_title(super_admin_client, db_session, test_env):
    """Cross-tenant export must include conversations whose title is NULL.

    Regression guard: the cross-tenant path used to reuse
    ``ConversationRepository.search_all(keyword="")`` whose ``title ILIKE '%%'``
    predicate drops NULL titles (ILIKE on NULL → NULL, not TRUE), silently
    losing untitled conversations from super_admin exports. The export must be
    lossless regardless of title.
    """
    await _seed_conversation(
        db_session,
        tenant_id=test_env.tenant_id,
        agent_id=_AGENT_ID,
        user_id=test_env.owner_user,
        title=None,
    )
    resp = await super_admin_client.get("/api/v1/exports/conversations", headers=AUTH)
    assert resp.status_code == 200
    rows = _parse_csv(resp.content)
    # header + 1 data row — the NULL-title conversation is included, not dropped
    assert len(rows) == 2


# ============================================================ usage


@pytest.mark.asyncio
async def test_export_usage_store_scope(app_client, db_session, test_env):
    """Store owner exports their tenant's usage events."""
    conv = await _seed_conversation(
        db_session,
        tenant_id=test_env.tenant_id,
        agent_id=_AGENT_ID,
        user_id=test_env.owner_user,
        title="用量对话",
    )
    await _seed_usage(
        db_session,
        tenant_id=test_env.tenant_id,
        conversation_id=conv.id,
        user_id=test_env.owner_user,
        total=42,
    )

    resp = await app_client.get("/api/v1/exports/usage", headers=AUTH)
    assert resp.status_code == 200, resp.text
    rows = _parse_csv(resp.content)
    assert rows[0] == [
        "date",
        "conversation_id",
        "model",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "cost",
        "customer_id",
    ]
    assert len(rows) == 2
    assert rows[1][5] == "42"  # total_tokens


@pytest.mark.asyncio
async def test_export_usage_tenant_isolation(app_client, db_session, test_env):
    """Usage export only contains this tenant's events."""
    other = "tnt-export-usage-other"
    conv_own = await _seed_conversation(
        db_session,
        tenant_id=test_env.tenant_id,
        agent_id=_AGENT_ID,
        user_id=test_env.owner_user,
        title="own",
    )
    conv_other = await _seed_conversation(
        db_session,
        tenant_id=other,
        agent_id=_AGENT_ID,
        user_id="cross-user",
        title="other",
    )
    await _seed_usage(
        db_session,
        tenant_id=test_env.tenant_id,
        conversation_id=conv_own.id,
        user_id=test_env.owner_user,
        total=10,
    )
    await _seed_usage(
        db_session,
        tenant_id=other,
        conversation_id=conv_other.id,
        user_id="cross-user",
        total=99,
    )

    resp = await app_client.get("/api/v1/exports/usage", headers=AUTH)
    assert resp.status_code == 200
    rows = _parse_csv(resp.content)
    assert len(rows) == 2  # header + 1
    assert rows[1][5] == "10"  # only own tenant's total


# ============================================================ logs


@pytest.mark.asyncio
async def test_export_logs_store_scope(app_client, db_session, test_env):
    """Store owner exports their tenant's audit logs."""
    await _seed_log(db_session, tenant_id=test_env.tenant_id, action="create", message="one")
    await _seed_log(db_session, tenant_id=test_env.tenant_id, action="update", message="two")

    resp = await app_client.get("/api/v1/exports/logs", headers=AUTH)
    assert resp.status_code == 200, resp.text
    rows = _parse_csv(resp.content)
    assert rows[0] == [
        "created_at",
        "user_id",
        "action",
        "resource_type",
        "resource_id",
        "message",
    ]
    assert len(rows) == 3
    assert {r[5] for r in rows[1:]} == {"one", "two"}


@pytest.mark.asyncio
async def test_export_logs_tenant_isolation(app_client, db_session, test_env):
    """Logs export cannot leak another tenant's rows."""
    other = "tnt-export-log-other"
    await _seed_log(db_session, tenant_id=test_env.tenant_id, message="visible")
    await _seed_log(db_session, tenant_id=other, message="secret")

    resp = await app_client.get("/api/v1/exports/logs", headers=AUTH)
    assert resp.status_code == 200
    rows = _parse_csv(resp.content)
    assert len(rows) == 2  # header + 1
    assert rows[1][5] == "visible"


@pytest.mark.asyncio
async def test_export_logs_super_admin_cross_tenant(
    super_admin_client, db_session, test_env
):
    """super_admin logs export spans every tenant."""
    other = "tnt-export-log-sa"
    await _seed_log(db_session, tenant_id=test_env.tenant_id, message="own")
    await _seed_log(db_session, tenant_id=other, message="other")

    resp = await super_admin_client.get("/api/v1/exports/logs", headers=AUTH)
    assert resp.status_code == 200
    rows = _parse_csv(resp.content)
    assert len(rows) == 3  # header + 2
    assert {r[5] for r in rows[1:]} == {"own", "other"}


# ============================================================ date range + errors


@pytest.mark.asyncio
async def test_export_logs_date_range(app_client, db_session, test_env):
    """date_from / date_to bound the export window."""
    now = datetime.now(UTC)
    await _seed_log(
        db_session,
        tenant_id=test_env.tenant_id,
        message="old",
        created_at=now - timedelta(days=40),
    )
    await _seed_log(
        db_session,
        tenant_id=test_env.tenant_id,
        message="recent",
        created_at=now - timedelta(days=1),
    )

    # Last 30 days (default window when no params given) → only "recent".
    resp = await app_client.get("/api/v1/exports/logs", headers=AUTH)
    assert resp.status_code == 200
    rows = _parse_csv(resp.content)
    assert len(rows) == 2  # header + recent
    assert rows[1][5] == "recent"


@pytest.mark.asyncio
async def test_export_logs_explicit_date_from(app_client, db_session, test_env):
    """An explicit date_from far in the past includes old rows too."""
    now = datetime.now(UTC)
    await _seed_log(
        db_session,
        tenant_id=test_env.tenant_id,
        message="old",
        created_at=now - timedelta(days=40),
    )

    since = (now - timedelta(days=50)).strftime("%Y-%m-%d")
    resp = await app_client.get(
        "/api/v1/exports/logs", params={"date_from": since}, headers=AUTH
    )
    assert resp.status_code == 200
    rows = _parse_csv(resp.content)
    assert len(rows) == 2  # header + old
    assert rows[1][5] == "old"


@pytest.mark.asyncio
async def test_export_unknown_entity_404(app_client):
    resp = await app_client.get("/api/v1/exports/widgets", headers=AUTH)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_export_bad_date_400(app_client):
    resp = await app_client.get(
        "/api/v1/exports/logs", params={"date_from": "not-a-date"}, headers=AUTH
    )
    assert resp.status_code == 400


# ============================================================ permissions


@pytest.mark.asyncio
async def test_export_logs_member_forbidden(member_client, db_session, test_env):
    """member has no logs:read → 403."""
    await _seed_log(db_session, tenant_id=test_env.tenant_id)
    resp = await member_client.get("/api/v1/exports/logs", headers=AUTH)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_export_customers_member_can_read(member_client, db_session, test_env):
    """member has customers:read (seeded in conftest) → export succeeds.

    This confirms the export reuses the SAME permission as the list endpoint
    (customers:read), so any role that can see the list can also export it —
    no new permission was introduced.
    """
    await _seed_customer(
        db_session, tenant_id=test_env.tenant_id, identity_key="13800000088", name="可见"
    )
    resp = await member_client.get("/api/v1/exports/customers", headers=AUTH)
    assert resp.status_code == 200
    rows = _parse_csv(resp.content)
    assert len(rows) == 2
    assert rows[1][0] == "可见"


@pytest.mark.asyncio
async def test_export_streaming_response_shape(app_client, db_session, test_env):
    """The response is a CSV attachment: right content-type + disposition."""
    await _seed_customer(
        db_session, tenant_id=test_env.tenant_id, identity_key="13800000099", name="流式"
    )
    resp = await app_client.get("/api/v1/exports/customers", headers=AUTH)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    assert "customers_" in resp.headers["content-disposition"]
    assert resp.headers["content-disposition"].endswith('.csv"')


# ============================================================ coverage gaps
#
# The matrix above left hq_staff entirely uncovered (only super_admin exercised
# the cross-tenant branch), had no 403 test for usage (the self-written
# PermissionError branch in _require_entity_read), and missed conversations
# tenant isolation + usage cross-tenant. These fill those gaps.


@pytest.mark.asyncio
async def test_export_usage_member_forbidden(member_client, db_session, test_env):
    """A role with neither billing:read nor wallet:read → 403.

    Covers the self-written ``raise PermissionError`` branch in
    ``_require_entity_read`` (exports.py): usage accepts EITHER perm, so we
    strip the member's seeded billing:read to force the deny path. Without this
    test the branch was unreachable by the suite.
    """
    conv = await _seed_conversation(
        db_session, tenant_id=test_env.tenant_id, agent_id=_AGENT_ID,
        user_id=test_env.owner_user, title="用量",
    )
    await _seed_usage(
        db_session, tenant_id=test_env.tenant_id, conversation_id=conv.id,
        user_id=test_env.owner_user,
    )
    # The member role is seeded with billing:read; strip it so the deny path
    # (neither billing:read nor wallet:read) is exercised. We remove by role
    # subject, not user_id — the policy is (role, tenant, obj, act).
    test_env.enforcer.remove_policy(
        "member", test_env.tenant_id, "billing", "read"
    )
    try:
        resp = await member_client.get("/api/v1/exports/usage", headers=AUTH)
        assert resp.status_code == 403
    finally:
        # Restore so other tests using the member role aren't poisoned.
        test_env.enforcer.add_policy(
            "member", test_env.tenant_id, "billing", "read"
        )


@pytest.mark.asyncio
async def test_export_usage_member_allowed_with_billing_read(
    member_client, db_session, test_env
):
    """member DOES have billing:read (seeded) → usage export 200.

    Pairs with the forbidden test above: proves the OR branch lets a billing:read
    holder through (without needing wallet:read).
    """
    conv = await _seed_conversation(
        db_session, tenant_id=test_env.tenant_id, agent_id=_AGENT_ID,
        user_id=test_env.owner_user, title="用量",
    )
    await _seed_usage(
        db_session, tenant_id=test_env.tenant_id, conversation_id=conv.id,
        user_id=test_env.owner_user, total=7,
    )
    resp = await member_client.get("/api/v1/exports/usage", headers=AUTH)
    assert resp.status_code == 200
    rows = _parse_csv(resp.content)
    assert len(rows) == 2  # header + 1
    assert rows[1][5] == "7"


@pytest.mark.asyncio
async def test_export_customers_hq_staff_cross_tenant(
    hq_staff_client, db_session, test_env
):
    """hq_staff (cross-tenant viewer) sees customers across tenants."""
    other = "tnt-export-cust-hq"
    await _seed_customer(
        db_session, tenant_id=test_env.tenant_id, identity_key="13800000001", name="本店"
    )
    await _seed_customer(
        db_session, tenant_id=other, identity_key="13900000002", name="他店"
    )
    resp = await hq_staff_client.get("/api/v1/exports/customers", headers=AUTH)
    assert resp.status_code == 200
    rows = _parse_csv(resp.content)
    assert {r[0] for r in rows[1:]} == {"本店", "他店"}


@pytest.mark.asyncio
async def test_export_logs_hq_staff_cross_tenant(
    hq_staff_client, db_session, test_env
):
    """hq_staff sees audit logs across tenants."""
    other = "tnt-export-log-hq"
    await _seed_log(db_session, tenant_id=test_env.tenant_id, message="own")
    await _seed_log(db_session, tenant_id=other, message="other")
    resp = await hq_staff_client.get("/api/v1/exports/logs", headers=AUTH)
    assert resp.status_code == 200
    rows = _parse_csv(resp.content)
    assert {r[5] for r in rows[1:]} == {"own", "other"}


@pytest.mark.asyncio
async def test_export_conversations_tenant_isolation(app_client, db_session, test_env):
    """A store's conversation export cannot include another tenant's rows."""
    other = "tnt-export-conv-iso"
    await _seed_conversation(
        db_session, tenant_id=test_env.tenant_id, agent_id=_AGENT_ID,
        user_id=test_env.owner_user, title="本店对话",
    )
    await _seed_conversation(
        db_session, tenant_id=other, agent_id=_AGENT_ID,
        user_id="cross-user", title="他店对话",
    )
    resp = await app_client.get("/api/v1/exports/conversations", headers=AUTH)
    assert resp.status_code == 200
    rows = _parse_csv(resp.content)
    titles = {r[0] for r in rows[1:]}
    assert "本店对话" in titles
    assert "他店对话" not in titles


@pytest.mark.asyncio
async def test_export_usage_super_admin_cross_tenant(
    super_admin_client, db_session, test_env
):
    """super_admin usage export spans every tenant."""
    other = "tnt-export-usage-sa"
    conv_own = await _seed_conversation(
        db_session, tenant_id=test_env.tenant_id, agent_id=_AGENT_ID,
        user_id=test_env.owner_user, title="own",
    )
    conv_other = await _seed_conversation(
        db_session, tenant_id=other, agent_id=_AGENT_ID,
        user_id="cross-user", title="other",
    )
    await _seed_usage(
        db_session, tenant_id=test_env.tenant_id, conversation_id=conv_own.id,
        user_id=test_env.owner_user, total=10,
    )
    await _seed_usage(
        db_session, tenant_id=other, conversation_id=conv_other.id,
        user_id="cross-user", total=99,
    )
    resp = await super_admin_client.get("/api/v1/exports/usage", headers=AUTH)
    assert resp.status_code == 200
    rows = _parse_csv(resp.content)
    totals = {r[5] for r in rows[1:]}
    assert totals == {"10", "99"}


@pytest.mark.asyncio
async def test_export_hq_staff_with_tenant_filter(
    hq_staff_client, db_session, test_env
):
    """hq_staff passing ?tenant_id narrows the export to that one tenant."""
    other = "tnt-export-hq-filter"
    await _seed_log(db_session, tenant_id=test_env.tenant_id, message="target")
    await _seed_log(db_session, tenant_id=other, message="excluded")
    resp = await hq_staff_client.get(
        "/api/v1/exports/logs",
        params={"tenant_id": test_env.tenant_id},
        headers=AUTH,
    )
    assert resp.status_code == 200
    rows = _parse_csv(resp.content)
    msgs = {r[5] for r in rows[1:]}
    assert "target" in msgs
    assert "excluded" not in msgs
