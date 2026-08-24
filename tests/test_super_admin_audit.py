"""Audit tests for the three highest-risk super-admin write paths (R4).

Covers (plan-super-admin-write-audit §5):
- Recharge: ``BillingService.recharge`` writes a ``billing.recharge`` SystemLog
  atomically with the business txn (record BEFORE commit — the user_service
  pattern, deliberately not booking_config's dangling commit→record).
- Pricing (POST/PUT/DELETE /billing/pricing): ``pricing.upsert`` / ``pricing.
  update`` / ``pricing.deactivate`` audits via the HTTP seam (real get_db
  request lifecycle) so the audit row's persistence is asserted the way
  booking_config's mock-kwargs tests failed to.
- Knowledge distribute/revoke: ``knowledge.distribute`` / ``knowledge.revoke``
  audits at the service seam, including the empty-group no-audit boundary.
- Read-side visibility: a store owner with logs:read sees the recharge audit
  via GET /logs; a foreign tenant's rows stay invisible.

All field assertions run against real SystemLog rows queried back from the
DB — never against mocked record kwargs (the booking_config lesson: mock
assertions cannot detect a dangling audit row that never persists).
"""

from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select

AUTH = {"Authorization": "Bearer fake"}


@pytest_asyncio.fixture
async def patched_enforcer(test_env, monkeypatch):
    """Point ``check()`` at ``test_env.enforcer`` for direct-service tests.

    Mirrors test_knowledge_backend.patched_enforcer (the fixture lives in that
    file, not conftest): conftest's _build_client does the same patch for HTTP
    tests, this one lets KnowledgeService called directly consult the test's
    seeded enforcer instead of the unrelated global one.
    """
    from app.core import casbin_enforcer as casbin_mod
    monkeypatch.setattr(casbin_mod, "get_enforcer", lambda: test_env.enforcer)
    yield test_env.enforcer


# ----------------------------------------------------------- helpers


async def _seed_wallet(db_session, tenant_id: str, balance: int = 0):
    """Insert a live wallet for a tenant with the given balance."""
    from app.models.wallet import Wallet

    w = Wallet(tenant_id=tenant_id, balance=balance, total_recharged=balance)
    db_session.add(w)
    await db_session.commit()
    await db_session.refresh(w)
    return w


async def _seed_pricing(db_session, model: str, in_price: Decimal, out_price: Decimal,
                        tenant_id: str | None = None):
    """Insert a ModelPricing row (platform default when tenant_id=None)."""
    from app.models.model_pricing import ModelPricing

    p = ModelPricing(
        tenant_id=tenant_id,
        model=model,
        input_price_per_1k=in_price,
        output_price_per_1k=out_price,
        is_active=True,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


async def _audit_rows(db_session, action: str) -> list:
    """All SystemLog rows for an action (empty list = no audit written)."""
    from app.models.log import SystemLog

    stmt = select(SystemLog).where(SystemLog.action == action)
    return list((await db_session.execute(stmt)).scalars().all())


async def _one_audit(db_session, action: str):
    """The single SystemLog row for an action — fails on zero or duplicates."""
    rows = await _audit_rows(db_session, action)
    assert len(rows) == 1, f"expected exactly 1 {action!r} audit row, got {len(rows)}"
    return rows[0]


def _bind_role(enforcer, user_id: str, role: str, tenant_id: str) -> None:
    """Bind a (user, tenant, role) + seed that tenant's knowledge policies.

    Mirrors test_knowledge_backend._bind_role: conftest only seeds policies for
    test_env.tenant_id, so direct-service tests on other tenants must add the
    knowledge read/create/delete/distribute set for the owner role themselves.
    """
    enforcer.add_role_for_user_in_domain(user_id, role, tenant_id)
    for obj, act in [
        ("knowledge", "read"), ("knowledge", "create"),
        ("knowledge", "delete"), ("knowledge", "distribute"),
    ]:
        enforcer.add_policy(role, tenant_id, obj, act)


async def _seed_knowledge_world(db_session) -> dict:
    """Minimal knowledge topology: two stores, one two-member group, one empty
    group, a store doc (t_a1) and a group doc (GroupA).

    Returns ids for assertions. Mirrors test_knowledge_backend's
    _seed_document_fixture but trimmed to what the audit cases need.
    """
    import uuid

    from app.models.document import Document
    from app.models.group import Group, GroupTenant
    from app.models.tenant import Tenant

    def _uid(prefix: str) -> str:
        return f"{prefix}-{uuid.uuid4().hex[:12]}"

    t_a1, t_a2 = Tenant(id=_uid("t"), name="A1"), Tenant(id=_uid("t"), name="A2")
    g_full, g_empty = Group(id=_uid("g"), name="FullGroup"), Group(id=_uid("g"), name="EmptyGroup")
    db_session.add_all([t_a1, t_a2, g_full, g_empty])
    await db_session.flush()
    db_session.add_all([
        GroupTenant(group_id=g_full.id, tenant_id=t_a1.id),
        GroupTenant(group_id=g_full.id, tenant_id=t_a2.id),
    ])
    store_doc = Document(
        tenant_id=t_a1.id, name="A1店FAQ", scope="store",
        content="x", status="indexed", chunk_count=1,
    )
    group_doc = Document(
        tenant_id=t_a1.id, name="A集团手册", scope="group", group_id=g_full.id,
        content="x", status="indexed", chunk_count=1,
    )
    db_session.add_all([store_doc, group_doc])
    await db_session.commit()
    await db_session.refresh(store_doc)
    await db_session.refresh(group_doc)
    return {
        "t_a1": t_a1.id, "t_a2": t_a2.id,
        "g_full": g_full.id, "g_empty": g_empty.id,
        "store_doc": store_doc.id, "group_doc": group_doc.id,
    }


# ----------------------------------------------------- recharge (service seam)


@pytest.mark.asyncio
async def test_recharge_writes_audit_row(db_session, test_env):
    """recharge() writes one billing.recharge row with the full accountability
    fields: operator, target tenant, amount/balance/remark, txn resource id."""
    from app.services.billing_service import BillingService

    await _seed_wallet(db_session, test_env.tenant_id, balance=100)
    txn = await BillingService(db_session).recharge(
        test_env.tenant_id, 500, operator_id="op-super", remark="五月活动充值"
    )

    log = await _one_audit(db_session, "billing.recharge")
    assert log.module == "billing"
    assert log.level == "info"
    assert log.user_id == "op-super"
    assert log.tenant_id == test_env.tenant_id
    assert log.resource_type == "wallet_transaction"
    # txn.id requires the repo's flush — proves record ran AFTER add (§4.7.7).
    assert log.resource_id == txn.id
    assert log.details_json == {
        "amount": 500, "balance_after": 600, "remark": "五月活动充值",
    }


@pytest.mark.asyncio
async def test_recharge_audit_failure_does_not_block(db_session, test_env, monkeypatch):
    """Best-effort contract: an exploding audit insert must not break the
    recharge — SAVEPOINT rolls back only the audit row, business commits."""
    import app.services.logging_service as logging_service_mod
    from app.services.billing_service import BillingService

    class _ExplodingLog:
        def __init__(self, **kwargs):
            raise RuntimeError("audit insert boom")

    monkeypatch.setattr(logging_service_mod, "SystemLog", _ExplodingLog)
    await _seed_wallet(db_session, test_env.tenant_id, balance=100)
    txn = await BillingService(db_session).recharge(
        test_env.tenant_id, 500, operator_id="op-super", remark="boom-test"
    )

    # Business txn committed and consistent.
    assert txn.balance_after == 600
    assert txn.type == "recharge"
    # Audit row absent (SAVEPOINT rollback swallowed by record).
    assert await _audit_rows(db_session, "billing.recharge") == []


# ----------------------------------------------------- pricing (HTTP seam)


@pytest.mark.asyncio
async def test_pricing_upsert_new_platform_row_audit(super_admin_client, db_session, test_env):
    """POST /pricing (new platform row) → pricing.upsert: no old_values, full
    new_values snapshot, scope=platform, tenant_id NULL, operator recorded."""
    resp = await super_admin_client.post(
        "/api/v1/billing/pricing",
        json={"model": "deepseek-chat",
              "input_price_per_1k": "1.0", "output_price_per_1k": "2.0"},
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    pid = resp.json()["id"]

    log = await _one_audit(db_session, "pricing.upsert")
    assert log.module == "billing"
    assert log.level == "info"
    assert log.user_id == test_env.owner_user  # super admin operator
    assert log.tenant_id is None  # platform-level
    assert log.resource_type == "model_pricing"
    assert log.resource_id == pid
    assert log.details_json == {"scope": "platform"}
    assert log.old_values is None
    assert log.new_values == {
        "tenant_id": None, "model": "deepseek-chat",
        "input_price_per_1k": "1.000000", "output_price_per_1k": "2.000000",
        "is_active": True,
    }


@pytest.mark.asyncio
async def test_pricing_upsert_existing_row_captures_old_values(super_admin_client, db_session):
    """Re-POST the same scope+model → the second audit carries the pre-change
    snapshot in old_values (update-in-place, not a duplicate row)."""
    for in_p, out_p in [("1.0", "2.0"), ("3.0", "4.0")]:
        resp = await super_admin_client.post(
            "/api/v1/billing/pricing",
            json={"model": "gpt-x", "input_price_per_1k": in_p,
                  "output_price_per_1k": out_p},
            headers=AUTH,
        )
        assert resp.status_code == 201, resp.text

    rows = await _audit_rows(db_session, "pricing.upsert")
    assert len(rows) == 2
    second = [r for r in rows if r.old_values is not None]
    assert len(second) == 1
    assert second[0].old_values["input_price_per_1k"] == "1.000000"
    assert second[0].old_values["output_price_per_1k"] == "2.000000"
    assert second[0].new_values["input_price_per_1k"] == "3.000000"
    assert second[0].new_values["output_price_per_1k"] == "4.000000"


@pytest.mark.asyncio
async def test_pricing_tenant_override_audit(super_admin_client, db_session, test_env):
    """POST /pricing with tenant_id → scope=tenant and the overridden tenant
    on the log row (so the store's logs:read users see they were re-priced)."""
    resp = await super_admin_client.post(
        "/api/v1/billing/pricing",
        json={"tenant_id": test_env.tenant_id, "model": "deepseek-chat",
              "input_price_per_1k": "5.0", "output_price_per_1k": "6.0"},
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text

    log = await _one_audit(db_session, "pricing.upsert")
    assert log.tenant_id == test_env.tenant_id
    assert log.details_json == {"scope": "tenant"}
    assert log.new_values["tenant_id"] == test_env.tenant_id


@pytest.mark.asyncio
async def test_pricing_update_audit_double_snapshot(super_admin_client, db_session):
    """PUT /pricing/{id} → pricing.update with before (from DB) and after
    (from payload) snapshots."""
    row = await _seed_pricing(db_session, "m-put", Decimal("1"), Decimal("2"))
    resp = await super_admin_client.put(
        f"/api/v1/billing/pricing/{row.id}",
        json={"model": "m-put", "input_price_per_1k": "9.0",
              "output_price_per_1k": "9.5"},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text

    log = await _one_audit(db_session, "pricing.update")
    assert log.level == "info"
    assert log.resource_id == row.id
    assert log.old_values["input_price_per_1k"] == "1.000000"
    assert log.old_values["output_price_per_1k"] == "2.000000"
    assert log.old_values["is_active"] is True
    assert log.new_values["input_price_per_1k"] == "9.000000"
    assert log.new_values["output_price_per_1k"] == "9.500000"
    assert log.new_values["is_active"] is True  # schema default


@pytest.mark.asyncio
async def test_pricing_deactivate_audit_warn(super_admin_client, db_session):
    """DELETE /pricing/{id} → pricing.deactivate at level=warn (destructive,
    mirroring user.delete) with the pre-deactivation snapshot preserved."""
    row = await _seed_pricing(db_session, "m-del", Decimal("7"), Decimal("8"),
                              tenant_id=None)
    resp = await super_admin_client.delete(
        f"/api/v1/billing/pricing/{row.id}", headers=AUTH
    )
    assert resp.status_code == 204, resp.text

    log = await _one_audit(db_session, "pricing.deactivate")
    assert log.level == "warn"
    assert log.resource_id == row.id
    assert log.old_values["is_active"] is True
    assert log.old_values["input_price_per_1k"] == "7.000000"
    assert log.new_values == {"is_active": False}


# ------------------------------------------- knowledge distribute / revoke


@pytest.mark.asyncio
async def test_distribute_by_tenant_list_audits_owner_too(
    patched_enforcer, db_session
):
    """Explicit tenant list → knowledge.distribute with the full target list,
    tenant_id NULL (batch, multi-target), issued by a non-super store owner
    (D4: audit is unconditional across roles)."""
    from app.schemas.document import DistributeRequest
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_knowledge_world(db_session)
    _bind_role(patched_enforcer, "u-owner-a1", "owner", ids["t_a1"])
    rows = await KnowledgeService(db_session).distribute_document(
        "u-owner-a1", ids["t_a1"], ids["store_doc"],
        DistributeRequest(target_tenant_ids=[ids["t_a2"]]),
        platform_role=None,
    )
    assert len(rows) == 1

    log = await _one_audit(db_session, "knowledge.distribute")
    assert log.module == "knowledge"
    assert log.level == "info"
    assert log.user_id == "u-owner-a1"
    assert log.tenant_id is None  # batch target — list lives in details (D6)
    assert log.resource_type == "knowledge_document"
    assert log.resource_id == ids["store_doc"]
    assert log.details_json == {
        "document_id": ids["store_doc"],
        "target_tenant_ids": [ids["t_a2"]],
        "distributed_count": 1,
    }


@pytest.mark.asyncio
async def test_distribute_by_group_audits_super_admin(db_session):
    """Group mode → details carry target_group_id (not a tenant list) and the
    expanded store count."""
    from app.schemas.document import DistributeRequest
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_knowledge_world(db_session)
    rows = await KnowledgeService(db_session).distribute_document(
        "u-super", ids["t_a1"], ids["group_doc"],
        DistributeRequest(target_group_id=ids["g_full"]),
        platform_role="super_admin",
    )
    assert len(rows) == 2  # both GroupA stores

    log = await _one_audit(db_session, "knowledge.distribute")
    assert log.user_id == "u-super"
    assert log.resource_id == ids["group_doc"]
    assert log.details_json == {
        "document_id": ids["group_doc"],
        "target_group_id": ids["g_full"],
        "distributed_count": 2,
    }


@pytest.mark.asyncio
async def test_distribute_to_empty_group_writes_no_audit(db_session):
    """Empty-group early-return (no business write) must NOT leave an audit
    row — a zero-action audit is noise (§4.7.5)."""
    from app.schemas.document import DistributeRequest
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_knowledge_world(db_session)
    rows = await KnowledgeService(db_session).distribute_document(
        "u-super", ids["t_a1"], ids["store_doc"],
        DistributeRequest(target_group_id=ids["g_empty"]),
        platform_role="super_admin",
    )
    assert rows == []
    assert await _audit_rows(db_session, "knowledge.distribute") == []


@pytest.mark.asyncio
async def test_revoke_distribution_audits_warn_with_target_tenant(db_session):
    """revoke → knowledge.revoke at warn with tenant_id = the store that lost
    the doc, so its logs:read users see the recall in their own audit page."""
    from app.schemas.document import DistributeRequest
    from app.services.knowledge_service import KnowledgeService

    ids = await _seed_knowledge_world(db_session)
    svc = KnowledgeService(db_session)
    rows = await svc.distribute_document(
        "u-super", ids["t_a1"], ids["store_doc"],
        DistributeRequest(target_tenant_ids=[ids["t_a2"]]),
        platform_role="super_admin",
    )
    dist_id = rows[0].id

    await svc.revoke_distribution(
        "u-auditor", ids["t_a1"], dist_id, platform_role="super_admin"
    )

    log = await _one_audit(db_session, "knowledge.revoke")
    assert log.module == "knowledge"
    assert log.level == "warn"
    assert log.user_id == "u-auditor"
    assert log.tenant_id == ids["t_a2"]  # the affected store, not the caller's
    assert log.resource_type == "knowledge_distribution"
    assert log.resource_id == dist_id
    assert log.details_json == {
        "document_id": ids["store_doc"],
        "target_tenant_id": ids["t_a2"],
    }


# ------------------------------------------------- read-side visibility


@pytest.mark.asyncio
async def test_store_owner_sees_recharge_audit_via_logs_api(
    app_client, db_session, test_env
):
    """The recharged store's owner (logs:read) finds the billing.recharge row
    via GET /logs?action=…; a foreign tenant's audit rows stay invisible."""
    from app.models.log import SystemLog
    from app.services.billing_service import BillingService

    await _seed_wallet(db_session, test_env.tenant_id, balance=0)
    await BillingService(db_session).recharge(
        test_env.tenant_id, 300, operator_id="op-super", remark=None
    )
    # A foreign tenant's recharge audit — must not leak into the owner's page.
    db_session.add(SystemLog(
        level="info", action="billing.recharge", module="billing",
        message="other tenant recharge", user_id="op-super",
        tenant_id="tnt-foreign", details_json={"amount": 1},
    ))
    await db_session.commit()

    resp = await app_client.get(
        "/api/v1/logs/", params={"action": "billing.recharge"}, headers=AUTH
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    [item] = body["items"]
    assert item["tenant_id"] == test_env.tenant_id
    assert item["details_json"]["amount"] == 300
