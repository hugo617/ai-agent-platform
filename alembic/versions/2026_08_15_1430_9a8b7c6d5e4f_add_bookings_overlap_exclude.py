"""add bookings EXCLUDE constraint (active-window overlap DB backstop)

Revision ID: 9a8b7c6d5e4f
Revises: b3f7a2c91d4e
Create Date: 2026-08-15 14:30:00.000000+00:00

booking-toctou-guard slice 01 — structural, database-level backstop for the
check-then-insert race in ``BookingService`` (plan:
harness/docs/plan-booking-toctou-guard.md §4.6 / §6 切片 01). Two concurrent
``create`` calls can both pass the application-level ``find_overlap`` check
and both land; this EXCLUDE constraint makes the second INSERT/UPDATE fail at
the DB, structurally:

    EXCLUDE USING gist (
      device_id WITH =,
      tstzrange(scheduled_start_at, scheduled_end_at, '[)') WITH &&
    ) WHERE (status IN ('pending', 'confirmed', 'in_service'))

``'[)'`` mirrors the application's left-closed/right-open overlap semantics
(back-to-back bookings do not conflict); the WHERE predicate mirrors
``_ACTIVE_STATES`` verbatim (cancelled/done/no_show release their slot the
moment their status changes — same semantics as today). NULL ``device_id``
never conflicts (NULL ≠ NULL in exclusion comparisons), matching
``find_overlap``.

A partial unique index could NOT express this: it only rejects identical keys
(same start instant), not partial interval overlap — see the archaeology in
plan §1 and app/models/booking.py.

Upgrade order:
1. Refuse-to-migrate pre-checks (mirrors the knowledge-foundation precedent):
   existing data must be clean before the constraint (and its backing GiST
   index) can be built. Two parallel counts, either > 0 → RuntimeError.
2. ``CREATE EXTENSION IF NOT EXISTS btree_gist`` (needed for
   ``device_id WITH =`` inside a GiST exclusion; the pgvector/pg16 image
   bundles contrib — same rationale as the vector extension migration).
3. ``ALTER TABLE ... ADD CONSTRAINT`` (raw SQL: alembic autogenerate does not
   support ExcludeConstraint).

Postgres-only by dialect guard, mirroring the vector-extension migration:
the SQLite test suite builds its schema via ``create_all`` and never runs
this chain; the constraint also cannot live in the ORM ``__table_args__``
because SQLite cannot compile the PG-dialect construct.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9a8b7c6d5e4f"
down_revision: str | Sequence[str] | None = "b3f7a2c91d4e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Slot-holding states, deliberately spelled as literals — a migration is
# frozen history and must not import live application code (a later refactor
# of app.repositories.booking would silently change what old migrations do).
# MUST stay in sync with ``_ACTIVE_STATES`` (app/repositories/booking.py) —
# tests/test_booking_overlap_migration_source.py reads this file's source and
# fails CI if the lists drift.
_ACTIVE_STATES_SQL = "('pending', 'confirmed', 'in_service')"

# Overlap predicate mirrors find_overlap's left-closed/right-open comparison
# (D4): a.start < b.end AND b.start < a.end — back-to-back windows don't hit.
_OVERLAP_PAIRS_SQL = f"""
SELECT COUNT(*) FROM (
  SELECT a.id FROM bookings a JOIN bookings b
    ON a.id < b.id AND a.device_id = b.device_id
   AND a.status IN {_ACTIVE_STATES_SQL}
   AND b.status IN {_ACTIVE_STATES_SQL}
   AND a.scheduled_start_at < b.scheduled_end_at
   AND b.scheduled_start_at < a.scheduled_end_at
) AS _overlap
"""

# Degenerate windows (end <= start) are refused too: building the backing
# GiST index evaluates tstzrange(start, end) which raises a native error for
# end < start, and end == start yields an empty range that silently never
# conflicts — either way it would violate _assert_window_valid's
# end > start invariant, so the data is bad regardless of the constraint.
_DEGENERATE_WINDOWS_SQL = f"""
SELECT COUNT(*) FROM bookings
 WHERE status IN {_ACTIVE_STATES_SQL}
   AND scheduled_end_at <= scheduled_start_at
"""

_ADD_CONSTRAINT_SQL = f"""
ALTER TABLE bookings ADD CONSTRAINT excl_bookings_active_no_overlap
  EXCLUDE USING gist (
    device_id WITH =,
    tstzrange(scheduled_start_at, scheduled_end_at, '[)') WITH &&
  )
  WHERE (status IN {_ACTIVE_STATES_SQL})
"""


def upgrade() -> None:
    bind = op.get_bind()

    overlap_pairs = bind.exec_driver_sql(_OVERLAP_PAIRS_SQL).scalar()
    degenerate_windows = bind.exec_driver_sql(_DEGENERATE_WINDOWS_SQL).scalar()
    if overlap_pairs or degenerate_windows:
        raise RuntimeError(
            f"Refusing to add exclusion constraint excl_bookings_active_no_overlap: "
            f"found {overlap_pairs} overlapping active booking pair(s) / "
            f"{degenerate_windows} degenerate active window(s). Fix the data first "
            f"(cancel or correct one of each conflicting pair; windows must have "
            f"scheduled_end_at > scheduled_start_at), then re-run this migration."
        )

    if bind.dialect.name != "sqlite":
        op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist;")
        op.execute(_ADD_CONSTRAINT_SQL)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.execute(
            "ALTER TABLE bookings "
            "DROP CONSTRAINT IF EXISTS excl_bookings_active_no_overlap;"
        )
    # btree_gist is deliberately NOT dropped: it is a shared, db-level
    # component (other future GiST needs may rely on it) and dropping it
    # would fail if anything else still uses its operator classes.
