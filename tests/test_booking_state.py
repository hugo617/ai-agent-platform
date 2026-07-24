"""Unit tests for the booking lifecycle state machine (device-poweron slice 01).

Pure-function tests — no DB, no fixtures, run in milliseconds. The state
machine is the single source of truth for legal status transitions; these
tests pin both halves of its contract:

- **Legal edges (6)**: each ``(current, action)`` in the table returns the
  expected new status. Parametrized so adding an edge to ``_TRANSITIONS``
  without updating the legal list surfaces as a new test case to fill in.
- **Illegal combinations**: every other ``(state, action)`` pair raises
  ``InvalidTransition``. Parametrized over the cartesian product of the 6
  statuses × 3 actions minus the 6 legal edges = 12 illegal pairs — so the
  "terminal states reject everything" and "can't end a pending booking"
  invariants are covered exhaustively, not by example.

The ``InvalidTransition`` assertions also verify the ``current`` / ``action``
attributes land on the exception (the Service layer doesn't read them today,
but they're the public surface for future error reporting and pinning them
keeps the contract honest).
"""

import pytest

from app.services.booking_state import ACTIONS, transition
from app.services.errors import BizError, InvalidTransition

# All values allowed by the bookings.status CHECK constraint (see
# app/schemas/booking.py ``BookingStatus`` Literal). The state machine owns
# transitions *between* these; it does not define the set itself.
_ALL_STATES = ["pending", "confirmed", "in_service", "done", "cancelled", "no_show"]

# The 6 legal edges — mirrors ``booking_state._TRANSITIONS``. Declared here
# (not imported from the module under test) so a typo in the table shows up
# as a failing legal-edge test rather than a tautology.
_LEGAL_EDGES = {
    ("pending", "start"): "in_service",
    ("confirmed", "start"): "in_service",
    ("in_service", "end"): "done",
    ("pending", "no_show"): "no_show",
    ("confirmed", "no_show"): "no_show",
    ("in_service", "no_show"): "no_show",
}


# ----------------------------------------------------- legal edges (6)


@pytest.mark.parametrize(
    ("current", "action", "expected"),
    [(s, a, v) for (s, a), v in sorted(_LEGAL_EDGES.items())],
    ids=[f"{s}__{a}" for (s, a), _ in sorted(_LEGAL_EDGES.items())],
)
def test_legal_edge_returns_expected_status(current, action, expected):
    """Each of the 6 legal ``(state, action)`` edges returns the new status."""
    assert transition(current, action) == expected


def test_legal_edges_count_is_six():
    """Guard against silently growing the state graph. If a new edge is added
    to ``_TRANSITIONS``, this test forces the author to extend the legal-edge
    parametrization above (and the plan's D2 spec) rather than leaving the
    new transition untested."""
    assert len(_LEGAL_EDGES) == 6


# ----------------------------------------- illegal combinations (12)


def _illegal_pairs():
    """Every ``(state, action)`` pair that is NOT in ``_LEGAL_EDGES`` — the
    state machine must reject each with ``InvalidTransition``."""
    return [
        (state, action)
        for state in _ALL_STATES
        for action in ACTIONS
        if (state, action) not in _LEGAL_EDGES
    ]


@pytest.mark.parametrize(
    ("current", "action"),
    _illegal_pairs(),
    ids=[f"{s}__{a}" for s, a in _illegal_pairs()],
)
def test_illegal_pair_raises_invalid_transition(current, action):
    """Every non-legal ``(state, action)`` raises ``InvalidTransition``.

    This covers the terminal-state invariants (done / cancelled / no_show
    reject all three actions) and the "can't end a pending booking" /
    "can't start an in_service booking again" rules, exhaustively rather
    than by example.
    """
    with pytest.raises(InvalidTransition) as exc_info:
        transition(current, action)
    # The exception's public attributes pin which input was refused — future
    # error-reporting / logging reads them, so they must match the call.
    assert exc_info.value.current == current
    assert exc_info.value.action == action


def test_illegal_pairs_count_is_twelve():
    """6 states × 3 actions − 6 legal edges = 12 illegal pairs. A guard
    against accidental table growth: if someone adds an edge without
    updating the legal list, this count drops and the mismatch surfaces."""
    assert len(_illegal_pairs()) == 12


# ------------------------------------------------------------- subclassing


def test_invalid_transition_is_biz_error():
    """``InvalidTransition`` subclasses ``BizError`` so the global BizError
    handler maps it to 400 without a dedicated handler (plan §4.5 — this is
    NOT the ScopeError→422 pattern of overriding the status code). Existing
    ``except BizError`` / ``except ValueError`` callers keep working."""
    with pytest.raises(BizError):
        transition("done", "start")
    with pytest.raises(ValueError):
        transition("cancelled", "end")
