"""Booking lifecycle state machine (device-poweron, slice 01).

A pure function over ``(current_status, action)`` pairs — the single source
of truth for which status transitions are legal. ``BookingService.start`` /
``end`` / ``no_show`` each call :func:`transition` first, then write the
corresponding timestamp / feedback column; the Service layer never inlines
``if status == ...`` checks, so the state graph lives in exactly one place.

Design (plan-device-poweron §0 D2/D3, §4.5):
- 6 legal edges, encoded as a ``{(state, action): new_state}`` table:
  ``start``      : {pending, confirmed} → in_service   (2)
  ``end``        : {in_service}         → done          (1)
  ``no_show``    : {pending, confirmed, in_service} → no_show (3)
- Any other ``(state, action)`` combination raises :class:`InvalidTransition`
  (a :class:`BizError` subclass → HTTP 400, NOT 409 — plan §0 D1; the repo
  has no 409 concept, and the existing ``BookingService.cancel`` refuses
  non-pending states with the same BizError → 400 pattern).
- Terminal states (``done`` / ``cancelled`` / ``no_show``) reject every
  action — the only way out of them is a fresh booking. ``cancelled`` is
  owned by ``/cancel`` (device-booking); the other two are owned here.

The function is deliberately DB-free and side-effect-free so it can be unit-
tested in milliseconds and reused by any caller (Service, CLI, future IoT
hook) without a session.
"""

from __future__ import annotations

from app.services.errors import InvalidTransition

# The three lifecycle actions exposed by device-poweron's endpoints. Kept as
# a frozenset (not an Enum) so the action strings match the URL path segments
# (``/start``, ``/end``, ``/no-show``) and the state-machine table keys
# without an extra mapping layer. ``no_show`` uses an underscore here and the
# endpoint translates the hyphenated URL; keeping the internal name consistent
# with the DB ``status`` CHECK constraint values avoids a second vocabulary.
ACTIONS: frozenset[str] = frozenset({"start", "end", "no_show"})

# The legal transition table — the state graph. Adding a new edge is the only
# change needed to extend the lifecycle; both ``transition`` and the unit
# tests derive their expectations from this map. Keys are ``(current, action)``
# and values are the resulting status.
_TRANSITIONS: dict[tuple[str, str], str] = {
    # start: a not-yet-serviced booking enters active service.
    ("pending", "start"): "in_service",
    ("confirmed", "start"): "in_service",
    # end: an in-service booking finishes successfully.
    ("in_service", "end"): "done",
    # no_show: the customer never showed / left mid-service. Allowed from any
    # non-terminal pre-done state — "pending/confirmed → no_show" = booked but
    # absent, "in_service → no_show" = started then abandoned.
    ("pending", "no_show"): "no_show",
    ("confirmed", "no_show"): "no_show",
    ("in_service", "no_show"): "no_show",
}


def transition(current: str, action: str) -> str:
    """Return the new status after applying ``action`` to ``current``.

    Raises :class:`InvalidTransition` (→ BizError 400) if the pair is not one
    of the 6 legal edges. Callers (``BookingService.start`` / ``end`` /
    ``no_show``) pass the booking's persisted ``status`` and the endpoint's
    action; on success they write the returned status back plus any side-effect
    column (``started_at`` / ``ended_at`` / ``feedback``).
    """
    try:
        return _TRANSITIONS[(current, action)]
    except KeyError as exc:
        raise InvalidTransition(current, action) from exc
