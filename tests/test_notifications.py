"""In-app notification tests (priority 54).

Covers:

- ``NotificationService`` create / list_for_user / unread_count / mark_read /
  mark_all_read at the service + repository layer.
- Multi-tenant + user isolation: a user sees their own targeted rows PLUS
  tenant-wide broadcasts (user_id IS NULL); they never see another user's
  targeted rows or another tenant's rows.
- API layer: GET /notifications, GET /notifications/unread-count,
  PUT /notifications/{id}/read (ownership → 404 for someone else's),
  PUT /notifications/read-all.
- Triggers: recharge creates a tenant-wide notification; role-change creates
  a targeted notification for the affected user.
- Scheduler job ``scan_balance_warnings``: creates balance_warning rows for
  low-balance wallets + dedupes (a second scan within 24h adds nothing).

Notifications are seeded via direct Notification inserts (the service wrapper
just adds an insert inside a savepoint) — simpler and deterministic.
"""

import pytest
from sqlalchemy import select

AUTH = {"Authorization": "Bearer fake"}


# ----------------------------------------------------------- helpers


async def _seed_notification(
    db_session,
    *,
    tenant_id,
    user_id=None,
    type_="system",
    title="hi",
    content="body",
    link=None,
    is_read=False,
):
    """Insert one Notification row directly and commit."""
    from app.models.notification import Notification

    db_session.add(
        Notification(
            tenant_id=tenant_id,
            user_id=user_id,
            type=type_,
            title=title,
            content=content,
            link=link,
            is_read=is_read,
        )
    )
    await db_session.commit()


async def _seed_wallet(db_session, tenant_id: str, *, balance: int, threshold: int = 0):
    """Insert a live wallet with the given balance + low-balance threshold."""
    from app.models.wallet import Wallet

    w = Wallet(
        tenant_id=tenant_id,
        balance=balance,
        total_recharged=balance,
        low_balance_threshold=threshold,
    )
    db_session.add(w)
    await db_session.commit()
    await db_session.refresh(w)
    return w


# ----------------------------------------------------- service / isolation


@pytest.mark.asyncio
async def test_user_sees_own_plus_tenant_wide(app_client, db_session, test_env):
    """A user sees their own targeted rows + tenant-wide broadcasts."""
    me = test_env.owner_user
    tnt = test_env.tenant_id
    await _seed_notification(db_session, tenant_id=tnt, user_id=me, title="own")
    # tenant-wide broadcast (user_id NULL) — visible to every user in the tenant.
    await _seed_notification(db_session, tenant_id=tnt, user_id=None, title="broadcast")

    resp = await app_client.get("/api/v1/notifications/", headers=AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    titles = {item["title"] for item in body["items"]}
    assert titles == {"own", "broadcast"}


@pytest.mark.asyncio
async def test_user_cannot_see_other_users_targeted(app_client, db_session, test_env):
    """A targeted notification for another user is NOT visible to me."""
    tnt = test_env.tenant_id
    await _seed_notification(
        db_session, tenant_id=tnt, user_id="someone-else", title="theirs"
    )
    # Plus a tenant-wide broadcast, which I SHOULD see.
    await _seed_notification(db_session, tenant_id=tnt, user_id=None, title="broadcast")

    resp = await app_client.get("/api/v1/notifications/", headers=AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "broadcast"


@pytest.mark.asyncio
async def test_cannot_see_other_tenant_notifications(app_client, db_session, test_env):
    """Tenant isolation: another tenant's rows (even broadcasts) are hidden."""
    # Foreign tenant broadcast — must be invisible.
    await _seed_notification(
        db_session, tenant_id="other-tenant", user_id=None, title="foreign"
    )

    resp = await app_client.get("/api/v1/notifications/", headers=AUTH)
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_unread_count_and_filter(app_client, db_session, test_env):
    """unread-count counts own + tenant-wide unread; ?unread_only filters."""
    me = test_env.owner_user
    tnt = test_env.tenant_id
    await _seed_notification(db_session, tenant_id=tnt, user_id=me, is_read=False)
    await _seed_notification(db_session, tenant_id=tnt, user_id=me, is_read=True)
    await _seed_notification(db_session, tenant_id=tnt, user_id=None, is_read=False)

    count = await app_client.get("/api/v1/notifications/unread-count", headers=AUTH)
    assert count.status_code == 200
    assert count.json()["count"] == 2  # own unread + broadcast unread

    only_unread = await app_client.get(
        "/api/v1/notifications/?unread_only=true", headers=AUTH
    )
    assert only_unread.status_code == 200
    assert only_unread.json()["total"] == 2


# ----------------------------------------------------- mark read


@pytest.mark.asyncio
async def test_mark_one_read(app_client, db_session, test_env):
    """PUT /notifications/{id}/read flips is_read for an owned notification."""
    me = test_env.owner_user
    tnt = test_env.tenant_id
    from app.models.notification import Notification

    db_session.add(
        Notification(
            tenant_id=tnt, user_id=me, type="system", title="t", content="c"
        )
    )
    await db_session.commit()
    nid = (
        await db_session.execute(
            select(Notification).where(Notification.title == "t")
        )
    ).scalar_one().id

    resp = await app_client.put(f"/api/v1/notifications/{nid}/read", headers=AUTH)
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_read"] is True

    # The unread count dropped.
    count = await app_client.get("/api/v1/notifications/unread-count", headers=AUTH)
    assert count.json()["count"] == 0


@pytest.mark.asyncio
async def test_mark_read_404_for_other_user(app_client, db_session, test_env):
    """Marking a notification targeted at another user → 404 (not visible)."""
    tnt = test_env.tenant_id
    from app.models.notification import Notification

    db_session.add(
        Notification(
            tenant_id=tnt, user_id="someone-else", type="system", title="t", content="c"
        )
    )
    await db_session.commit()
    nid = (
        await db_session.execute(
            select(Notification).where(Notification.title == "t")
        )
    ).scalar_one().id

    resp = await app_client.put(f"/api/v1/notifications/{nid}/read", headers=AUTH)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_mark_all_read(app_client, db_session, test_env):
    """PUT /notifications/read-all clears every visible unread notification."""
    me = test_env.owner_user
    tnt = test_env.tenant_id
    await _seed_notification(db_session, tenant_id=tnt, user_id=me, is_read=False)
    await _seed_notification(db_session, tenant_id=tnt, user_id=None, is_read=False)

    resp = await app_client.put("/api/v1/notifications/read-all", headers=AUTH)
    assert resp.status_code == 200, resp.text
    assert resp.json()["count"] == 0  # remaining unread

    only_unread = await app_client.get(
        "/api/v1/notifications/?unread_only=true", headers=AUTH
    )
    assert only_unread.json()["total"] == 0


@pytest.mark.asyncio
async def test_broadcast_read_is_per_user(db_session, test_env):
    """One user marking a broadcast read does NOT mark it read for others.

    This is the core reason ``notification_reads`` exists: a broadcast row
    (user_id NULL) is shared by the whole tenant, so the read state must be
    per-user. Before the fix, ``mark_all_read`` flipped ``is_read`` on the
    shared row and every other user's bell went silent too.
    """
    tnt = test_env.tenant_id
    user_a = test_env.owner_user
    user_b = "another-member"

    # Seed a tenant-wide broadcast (user_id NULL).
    await _seed_notification(db_session, tenant_id=tnt, user_id=None, title="broadcast")

    from app.services.notification_service import NotificationService

    svc = NotificationService(db_session)

    # User A marks all read — the broadcast is now read for A.
    await svc.mark_all_read(user_id=user_a, tenant_id=tnt)
    unread_a = await svc.unread_count(user_id=user_a, tenant_id=tnt)
    assert unread_a == 0  # A has nothing unread

    # User B still sees the broadcast as unread (A's read is per-user).
    unread_b = await svc.unread_count(user_id=user_b, tenant_id=tnt)
    assert unread_b == 1

    # B marks the broadcast read via mark_read; A's state is unaffected.
    rows_b, _ = await svc.list_for_user(user_id=user_b, tenant_id=tnt)
    broadcast = next(r for r in rows_b if r.user_id is None)
    await svc.mark_read(
        notification_id=broadcast.id, user_id=user_b, tenant_id=tnt
    )
    unread_a_after = await svc.unread_count(user_id=user_a, tenant_id=tnt)
    assert unread_a_after == 0  # A still read (her record untouched by B)
    unread_b_after = await svc.unread_count(user_id=user_b, tenant_id=tnt)
    assert unread_b_after == 0  # B now read it too


# ----------------------------------------------------- triggers


@pytest.mark.asyncio
async def test_recharge_creates_notification(app_client, db_session, test_env):
    """BillingService.recharge fires a tenant-wide recharge notification."""
    await _seed_wallet(db_session, test_env.tenant_id, balance=0)

    from app.services.billing_service import BillingService

    txn = await BillingService(db_session).recharge(
        tenant_id=test_env.tenant_id,
        amount=500,
        operator_id="admin",
    )
    assert txn.balance_after == 500

    from app.models.notification import Notification

    rows = (
        await db_session.execute(
            select(Notification).where(
                Notification.type == "recharge"
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    # tenant-wide (user_id NULL) so owner + admins all see it.
    assert rows[0].user_id is None
    assert "500" in rows[0].content


@pytest.mark.asyncio
async def test_role_change_creates_notification(app_client, db_session, test_env):
    """MemberService.update_role fires a role_change notification for the user."""
    from app.models.tenant import User, UserTenant

    target = "target-user"
    db_session.add(User(id=target, email="t@example.com", status="active"))
    db_session.add(
        UserTenant(user_id=target, tenant_id=test_env.tenant_id, role="member")
    )
    await db_session.commit()
    test_env.enforcer.add_role_for_user_in_domain(target, "member", test_env.tenant_id)

    from app.schemas.user import MemberUpdate
    from app.services.member_service import MemberService

    await MemberService(db_session).update_role(
        actor_id=test_env.owner_user,
        tenant_id=test_env.tenant_id,
        target_user_id=target,
        payload=MemberUpdate(role="admin"),
        platform_role=None,
    )

    from app.models.notification import Notification

    row = (
        await db_session.execute(
            select(Notification).where(
                Notification.type == "role_change"
            )
        )
    ).scalar_one()
    assert row.user_id == target  # targeted at the affected user
    assert "admin" in row.content


@pytest.mark.asyncio
async def test_notification_failure_does_not_break_recharge(db_session, test_env):
    """A broken notification insert must not abort the committed recharge.

    NotificationService.create wraps the insert in begin_nested + try/except,
    so a DB error during the notification insert rolls back ONLY the savepoint
    and the surrounding recharge transaction stays committed. We force a DB-
    level failure (a too-long title that violates the column's VARCHAR(200))
    so the real safety path is exercised, not a stubbed one.
    """
    await _seed_wallet(db_session, test_env.tenant_id, balance=0)

    from app.services import notification_service as ns_mod
    from app.services.billing_service import BillingService

    # Patch the repo insert to inject an over-long title through the real path.
    # The repo flush fails on String(200); begin_nested rolls back the
    # savepoint; the exception is swallowed — the recharge stays committed.
    original = ns_mod.NotificationRepository.create

    async def _bad_create(self, notification):  # noqa: ANN001
        notification.title = "x" * 10_000  # violates String(200)
        return await original(self, notification)

    ns_mod.NotificationRepository.create = _bad_create  # type: ignore[method-assign]
    try:
        # Despite the notification insert failing, recharge must succeed.
        txn = await BillingService(db_session).recharge(
            tenant_id=test_env.tenant_id, amount=100, operator_id="admin"
        )
        assert txn.balance_after == 100
    finally:
        ns_mod.NotificationRepository.create = original  # type: ignore[method-assign]


# ----------------------------------------------------- scheduler job


@pytest.mark.asyncio
async def test_scan_balance_warnings_creates_and_dedupes(db_session, test_env):
    """scan_balance_warnings warns low-balance wallets + dedupes within 24h.

    Calls the job function directly (no cron wait) with a session factory bound
    to the same test engine. Two low-balance wallets get warned; a second scan
    within the dedupe window adds nothing. Seeding uses the shared db_session
    (StaticPool single connection) so the job sees the committed rows.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    # A second tenant + its own low-balance wallet.
    from app.models.tenant import Tenant

    other_tnt = "tnt-other-warn"
    db_session.add(Tenant(id=other_tnt, name="Other"))
    await db_session.commit()

    # Two low-balance wallets (balance < threshold), one per tenant.
    await _seed_wallet(db_session, test_env.tenant_id, balance=5, threshold=100)
    await _seed_wallet(db_session, other_tnt, balance=10, threshold=50)
    # Healthy wallet (balance above threshold) in a third tenant — must NOT warn.
    healthy_tnt = "tnt-healthy-warn"
    db_session.add(Tenant(id=healthy_tnt, name="Healthy"))
    await db_session.commit()
    await _seed_wallet(db_session, healthy_tnt, balance=500, threshold=100)

    from app.core.scheduler import scan_balance_warnings

    first = await scan_balance_warnings(factory)
    assert first == 2  # two low-balance wallets warned

    # Second scan within 24h dedupes → zero new warnings.
    second = await scan_balance_warnings(factory)
    assert second == 0

    from app.models.notification import Notification

    rows = (
        await db_session.execute(
            select(Notification).where(
                Notification.type == "balance_warning"
            )
        )
    ).scalars().all()
    assert len(rows) == 2
    # Each warning is tenant-wide (user_id NULL).
    assert all(r.user_id is None for r in rows)


# ----------------------------------------------------- scheduler lifecycle


@pytest.mark.asyncio
async def test_scheduler_disabled_in_tests():
    """SCHEDULER_ENABLED defaults to False, so init_scheduler is a no-op.

    This is the test-safety invariant: create_app() is called per-test, and
    a real scheduler.start() on each call would raise 'already running'.
    """
    from app.core import scheduler as sched_mod

    assert sched_mod._SCHEDULER_ENABLED is False
    # init_scheduler must be idempotent + a no-op when disabled.
    instance = sched_mod.init_scheduler()
    assert instance.running is False
    # Calling again is still safe.
    sched_mod.init_scheduler()
    assert sched_mod.scheduler.running is False
