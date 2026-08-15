"""Postgres-gated tests for the bookings active-window EXCLUDE constraint.

booking-toctou-guard slice 01 (plan: harness/docs/plan-booking-toctou-guard.md
§4.6, cases ①-⑤). The constraint (``excl_bookings_active_no_overlap``, held by
migration ``9a8b7c6d5e4f``) is a PG-dialect construct, so these tests only run
when ``DATABASE_URL`` points at a real Postgres — the SQLite suite skips the
whole module. CI runs this file in the ``migrations`` job right after
``alembic upgrade head`` + ``alembic check``, so the schema under test is the
real migration product, not ORM ``create_all``.

Deterministic concurrency pattern (no timing roulette): conn1 opens a
transaction and INSERTs row A without committing → conn2 INSERTs an
overlapping row B, which BLOCKS on the exclusion constraint → conn1 commits →
conn2's INSERT fails with an exclusion violation. If the constraint were
missing, both inserts would succeed and the ``pytest.raises`` blocks below
would fail loudly.

Local replay:
    docker-compose up -d && alembic upgrade head
    DATABASE_URL=postgresql+psycopg://aap:aap_secret@localhost:5433/aap \
        pytest tests/test_booking_overlap_pg.py -v
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import bindparam, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

# Mapper completeness: case ⑥ instantiates the real BookingService, whose
# Device/Customer relationships resolve string targets (e.g. Device →
# DeviceModel) at first session use. This file deliberately does NOT import
# the app assembly (conftest does that for the SQLite suite); importing the
# model modules here registers every mapper the service touches so
# ``configure_mappers`` can't fail mid-race.
from app.models import (  # noqa: F401  (imported for mapper registration)
    booking,
    customer,
    device,
    device_model,
    tenant,
)
from app.repositories.booking import _ACTIVE_STATES
from app.schemas.booking import BookingCreate
from app.services.booking_service import _EXCLUSION_CONFLICT_MESSAGE, BookingService
from app.services.errors import BizError

# The active-count helper below imports the application's slot-holding state
# list so its口径 follows the single source (a test file, unlike a migration,
# may import live code) — the DB semantics themselves are what this file
# asserts, per plan D2.
pytestmark = pytest.mark.skipif(
    "postgresql" not in os.environ.get("DATABASE_URL", ""),
    reason=(
        "EXCLUDE constraint is Postgres-only; needs DATABASE_URL pointing at "
        "a Postgres that has the migration chain applied"
    ),
)

# Fixed booking day — far in the future so seeded rows never collide with
# anything a dev DB might contain.
_DAY = datetime(2030, 1, 15, tzinfo=UTC)


def _at(hour: float) -> datetime:
    """A timestamp on the fixed day (``_at(10.5)`` → 10:30 UTC)."""
    return _DAY + timedelta(hours=hour)


async def _insert_booking(
    conn: AsyncConnection,
    tenant_id: str,
    device_id: str | None,
    status: str,
    start: datetime,
    end: datetime,
) -> None:
    await conn.execute(
        text(
            "INSERT INTO bookings "
            "(id, tenant_id, device_id, status, scheduled_start_at, scheduled_end_at) "
            "VALUES (:id, :tenant, :device, :status, :start, :end)"
        ),
        {
            "id": f"bk-{uuid.uuid4().hex[:20]}",
            "tenant": tenant_id,
            "device": device_id,
            "status": status,
            "start": start,
            "end": end,
        },
    )


async def _commit_soon(conn: AsyncConnection, delay: float = 0.25) -> None:
    """Commit ``conn`` from a background task while another connection's
    INSERT is (or is about to be) blocked on the exclusion constraint."""
    await asyncio.sleep(delay)
    await conn.commit()


@pytest.fixture()
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(os.environ["DATABASE_URL"])
    try:
        yield eng
    finally:
        # dispose() also rolls back any connection a failing test leaked open.
        await eng.dispose()


@pytest.fixture()
async def seeded(engine: AsyncEngine) -> AsyncIterator[SimpleNamespace]:
    """One tenant + device_model + device chain, marker-unique; torn down in
    ``finally`` so failed tests don't pollute the shared dev DB."""
    marker = uuid.uuid4().hex[:12]
    tenant_id = f"toctou-t-{marker}"
    model_id = f"toctou-dm-{marker}"
    device_id = f"toctou-dv-{marker}"
    async with engine.connect() as conn:
        await conn.execute(
            text("INSERT INTO tenants (id, name) VALUES (:id, :n)"),
            {"id": tenant_id, "n": f"toctou-pg-test-{marker}"},
        )
        await conn.execute(
            text(
                "INSERT INTO device_models (id, name, unit_cost) "
                "VALUES (:id, :n, 0)"
            ),
            {"id": model_id, "n": f"toctou-model-{marker}"},
        )
        await conn.execute(
            text(
                "INSERT INTO devices (id, tenant_id, model_id, serial_number) "
                "VALUES (:id, :tenant, :model, :serial)"
            ),
            {
                "id": device_id,
                "tenant": tenant_id,
                "model": model_id,
                "serial": f"TOCTOU-PG-{marker}",
            },
        )
        await conn.commit()
    try:
        yield SimpleNamespace(tenant_id=tenant_id, device_id=device_id)
    finally:
        async with engine.connect() as conn:
            await conn.execute(
                text("DELETE FROM bookings WHERE tenant_id = :t"),
                {"t": tenant_id},
            )
            # cascades to devices (bookings already gone above)
            await conn.execute(
                text("DELETE FROM tenants WHERE id = :t"), {"t": tenant_id}
            )
            await conn.execute(
                text("DELETE FROM device_models WHERE id = :m"), {"m": model_id}
            )
            await conn.commit()


async def _active_booking_count(engine: AsyncEngine, device_id: str) -> int:
    async with engine.connect() as conn:
        return (
            await conn.execute(
                text(
                    "SELECT COUNT(*) FROM bookings "
                    "WHERE device_id = :d AND status IN :states"
                ).bindparams(bindparam("states", _ACTIVE_STATES, expanding=True)),
                {"d": device_id},
            )
        ).scalar_one()


@pytest.mark.asyncio
async def test_concurrent_overlapping_inserts_exactly_one_succeeds(
    engine: AsyncEngine, seeded: SimpleNamespace
) -> None:
    """Case ①: conn1's [10,12) is inserted but uncommitted; conn2's
    overlapping [11,13) INSERT blocks on the constraint, then fails once
    conn1 commits — the race window the application check cannot close is
    closed structurally by the DB, and exactly one row survives."""
    async with engine.connect() as c1, engine.connect() as c2:
        await _insert_booking(c1, seeded.tenant_id, seeded.device_id, "pending", _at(10), _at(12))
        committer = asyncio.create_task(_commit_soon(c1))
        try:
            with pytest.raises(IntegrityError) as excinfo:
                await _insert_booking(
                    c2, seeded.tenant_id, seeded.device_id, "pending", _at(11), _at(13)
                )
        finally:
            # even when the raises-assertion fails, let the commit land so
            # the leaked-task warning can't mask the real failure
            await committer
    # exclusion_violation — proves it is THIS constraint that rejected, not
    # some other integrity rule.
    assert getattr(excinfo.value.orig, "sqlstate", None) == "23P01"
    assert await _active_booking_count(engine, seeded.device_id) == 1


@pytest.mark.asyncio
async def test_back_to_back_windows_both_succeed(
    engine: AsyncEngine, seeded: SimpleNamespace
) -> None:
    """Case ②: '[)' left-closed/right-open — [10,12) followed by [12,14) does
    NOT conflict (mirrors find_overlap's boundary semantics, plan D4)."""
    async with engine.connect() as conn:
        await _insert_booking(conn, seeded.tenant_id, seeded.device_id, "pending", _at(10), _at(12))
        await _insert_booking(conn, seeded.tenant_id, seeded.device_id, "pending", _at(12), _at(14))
        await conn.commit()
    assert await _active_booking_count(engine, seeded.device_id) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("released_state", ["cancelled", "done", "no_show"])
async def test_released_state_window_is_reusable(
    engine: AsyncEngine, seeded: SimpleNamespace, released_state: str
) -> None:
    """Case ③: cancelled/done/no_show rows are outside the constraint's
    predicate — the exact same window can be rebooked immediately (user
    story 2: zero semantic change vs today)."""
    async with engine.connect() as conn:
        await _insert_booking(
            conn, seeded.tenant_id, seeded.device_id, released_state, _at(10), _at(12)
        )
        await conn.commit()
    async with engine.connect() as conn:
        await _insert_booking(conn, seeded.tenant_id, seeded.device_id, "pending", _at(10), _at(12))
        await conn.commit()
    assert await _active_booking_count(engine, seeded.device_id) == 1


@pytest.mark.asyncio
async def test_update_reschedule_into_occupied_window_rejected(
    engine: AsyncEngine, seeded: SimpleNamespace
) -> None:
    """Case ④: the constraint also guards UPDATE — moving booking B from
    [14,16) into A's [10,12) window (as [11,13)) fails; reschedule has no
    blind spot (plan D6)."""
    booking_a = f"bk-{uuid.uuid4().hex[:20]}"
    booking_b = f"bk-{uuid.uuid4().hex[:20]}"
    async with engine.connect() as conn:
        await conn.execute(
            text(
                "INSERT INTO bookings "
                "(id, tenant_id, device_id, status, scheduled_start_at, scheduled_end_at) "
                "VALUES (:id, :tenant, :device, 'pending', :start, :end)"
            ),
            {"id": booking_a, "tenant": seeded.tenant_id, "device": seeded.device_id,
             "start": _at(10), "end": _at(12)},
        )
        await conn.execute(
            text(
                "INSERT INTO bookings "
                "(id, tenant_id, device_id, status, scheduled_start_at, scheduled_end_at) "
                "VALUES (:id, :tenant, :device, 'pending', :start, :end)"
            ),
            {"id": booking_b, "tenant": seeded.tenant_id, "device": seeded.device_id,
             "start": _at(14), "end": _at(16)},
        )
        await conn.commit()
    async with engine.connect() as conn:
        with pytest.raises(IntegrityError) as excinfo:
            await conn.execute(
                text(
                    "UPDATE bookings SET scheduled_start_at = :start, "
                    "scheduled_end_at = :end WHERE id = :id"
                ),
                {"id": booking_b, "start": _at(11), "end": _at(13)},
            )
        assert getattr(excinfo.value.orig, "sqlstate", None) == "23P01"


@pytest.mark.asyncio
async def test_null_device_never_conflicts(
    engine: AsyncEngine, seeded: SimpleNamespace
) -> None:
    """Case ⑤: NULL device_id rows never conflict (NULL ≠ NULL in exclusion
    comparisons) — a device's historical rows (device soft-deleted → FK SET
    NULL) must not hold a slot (mirrors find_overlap)."""
    async with engine.connect() as conn:
        await _insert_booking(conn, seeded.tenant_id, None, "pending", _at(10), _at(12))
        await _insert_booking(conn, seeded.tenant_id, None, "pending", _at(10), _at(12))
        await conn.commit()
    async with engine.connect() as conn:
        n = (
            await conn.execute(
                text(
                    "SELECT COUNT(*) FROM bookings "
                    "WHERE tenant_id = :t AND device_id IS NULL"
                ),
                {"t": seeded.tenant_id},
            )
        ).scalar_one()
        assert n == 2


async def _await_blocked_insert(engine: AsyncEngine, timeout: float = 10.0) -> None:
    """Block until some backend is waiting on a lock mid-``INSERT INTO
    bookings`` — i.e. the service-path INSERT of case ⑥ has really parked on
    the exclusion constraint (not merely not-scheduled-yet). Deterministic
    handshake replacing a ``sleep`` guess; fails loudly if it never blocks."""
    waited = 0.0
    while waited < timeout:
        async with engine.connect() as probe:
            n = (
                await probe.execute(
                    text(
                        "SELECT COUNT(*) FROM pg_stat_activity "
                        "WHERE wait_event_type = 'Lock' "
                        "AND query LIKE 'INSERT INTO bookings%'"
                    )
                )
            ).scalar_one()
        if n:
            return
        await asyncio.sleep(0.05)
        waited += 0.05
    pytest.fail("service-path INSERT never blocked on the exclusion constraint")


@pytest.mark.asyncio
async def test_service_path_race_maps_to_bizerror(
    engine: AsyncEngine, seeded: SimpleNamespace
) -> None:
    """Case ⑥ (slice 02): the full service-path race chain on real PG —
    conn1 holds an UNCOMMITTED active [10,12) row while a separate session's
    ``BookingService.create`` books overlapping [11,13). Under read committed
    the application-layer ``find_overlap`` cannot see the uncommitted row, so
    the friendly check passes; the INSERT then blocks on the exclusion
    constraint until conn1 commits and fails with 23P01 — which the service
    must translate to a BizError (→ 400), never leak the IntegrityError (→
    500). The exact-message assertion pins WHICH line fired: the application
    layer's message names the conflicting booking id, the DB backstop's (D8)
    deliberately doesn't — so this test cannot pass via the friendly check.

    Uses the super_admin write path (payload tenant_id + require bypass) so
    the race reaches the INSERT without casbin setup; ``created_by`` has a
    real FK to users.id, so the actor row is seeded too (keeps the only
    failure mode of the INSERT the exclusion constraint itself).
    """
    actor_id = f"toctou-u-{uuid.uuid4().hex[:12]}"
    async with engine.connect() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, email, avatar, status) "
                "VALUES (:id, :e, '', 'active')"
            ),
            {"id": actor_id, "e": f"{actor_id}@example.invalid"},
        )
        await conn.commit()
    try:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.connect() as c1, session_factory() as svc_session:
            await _insert_booking(
                c1, seeded.tenant_id, seeded.device_id, "pending", _at(10), _at(12)
            )
            service = BookingService(svc_session)
            create_task = asyncio.create_task(
                service.create(
                    actor_id=actor_id,
                    tenant_id=None,
                    payload=BookingCreate(
                        tenant_id=seeded.tenant_id,
                        device_id=seeded.device_id,
                        customer_id=None,
                        scheduled_start_at=_at(11),
                        scheduled_end_at=_at(13),
                    ),
                    platform_role="super_admin",
                )
            )
            # Deterministic: only commit conn1 once the service INSERT is
            # actually parked on the constraint (find_overlap has already
            # passed on the invisible row by then).
            await _await_blocked_insert(engine)
            await c1.commit()
            with pytest.raises(BizError) as excinfo:
                await create_task
            assert str(excinfo.value) == _EXCLUSION_CONFLICT_MESSAGE
        assert await _active_booking_count(engine, seeded.device_id) == 1
    finally:
        async with engine.connect() as conn:
            await conn.execute(
                text("DELETE FROM users WHERE id = :id"), {"id": actor_id}
            )
            await conn.commit()
