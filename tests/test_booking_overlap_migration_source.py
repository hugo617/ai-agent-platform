"""Same-source anti-drift guard for the bookings EXCLUDE constraint states.

booking-toctou-guard slice 01 (plan §4.6, review finding 🟡 → adopted). The
slot-holding state list lives in THREE places **by design** — a migration is
frozen history and must not import live application code (a later refactor of
``app.repositories.booking`` would silently change what old migrations do):

  1. ``app.repositories.booking._ACTIVE_STATES`` — application-level check
  2. migration ``9a8b7c6d5e4f``'s refuse-to-migrate pre-check SQL
  3. migration ``9a8b7c6d5e4f``'s constraint WHERE predicate — DB backstop

The migration centralizes its copy in the module constant
``_ACTIVE_STATES_SQL`` and interpolates it into all three SQL sites. This
test reads the migration's SOURCE and fails if that constant drifts from
``_ACTIVE_STATES``, or if any SQL site stops referencing it — so a future
state-machine change that forgets the DB guard turns CI red instead of
silently splitting semantics between the two defense layers (plan D2/D7).

SQLite-resident by construction: it parses source text, touches no database.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.repositories.booking import _ACTIVE_STATES

_MIGRATION_GLOB = "*_add_bookings_overlap_exclude.py"
# How many SQL sites in the migration interpolate the state-list constant:
# overlap-pair pre-check × 2 (a-side + b-side), degenerate-window pre-check
# × 1, constraint WHERE predicate × 1.
_EXPECTED_CONSTANT_SITES = 4


def _migration_source() -> str:
    versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    matches = sorted(versions_dir.glob(_MIGRATION_GLOB))
    assert len(matches) == 1, (
        f"expected exactly one {_MIGRATION_GLOB} migration, "
        f"found {[m.name for m in matches]}"
    )
    return matches[0].read_text()


def _migration_code() -> str:
    """The migration's source minus its module docstring — the docstring
    quotes the constraint DDL verbatim for humans, which is exactly the
    hand-spelled illustration these tests must not mistake for code."""
    parts = _migration_source().split('"""', 2)
    assert len(parts) == 3, "migration module docstring not found as expected"
    return parts[2]


def test_migration_state_list_matches_application_active_states() -> None:
    """The migration's ``_ACTIVE_STATES_SQL`` constant must enumerate exactly
    the application's slot-holding states — the DB guard and the application
    check stay one semantic (plan D2)."""
    match = re.search(
        r"_ACTIVE_STATES_SQL = \"\(([^)]*)\)\"", _migration_code()
    )
    assert match is not None, "_ACTIVE_STATES_SQL constant not found in migration"
    literal_states = re.findall(r"'([^']+)'", match.group(1))
    assert tuple(literal_states) == _ACTIVE_STATES, (
        f"migration state list {literal_states} drifted from application "
        f"_ACTIVE_STATES {_ACTIVE_STATES} — the DB backstop and the "
        "application check must reject/accept the same states (plan D2); "
        "update both lists in the same commit"
    )


def test_every_migration_sql_site_uses_the_state_constant() -> None:
    """No SQL site in the migration may spell the state list out by hand —
    every predicate must flow through ``_ACTIVE_STATES_SQL`` so the constant
    above is the single point that can drift (and get caught)."""
    code = _migration_code()
    sites = code.count("{_ACTIVE_STATES_SQL}")
    assert sites == _EXPECTED_CONSTANT_SITES, (
        f"expected {_EXPECTED_CONSTANT_SITES} SQL sites interpolating "
        f"_ACTIVE_STATES_SQL, found {sites} — a site may have been rewritten "
        "with a hand-spelled state list"
    )
    # And no hand-spelled state list may bypass the constant in executable SQL.
    hand_spelled = re.findall(r"status IN \('pending'[^)]*\)", code)
    assert not hand_spelled, (
        f"hand-spelled state list in migration SQL: {hand_spelled} — route it "
        "through _ACTIVE_STATES_SQL"
    )
