"""Shared datetime helpers for query-param parsing + cross-DB normalisation.

Two concerns that recur across endpoints (``/logs``, ``/exports``, and any
future time-filtered read) live here so they're defined once:

- ``parse_iso_dt`` — turn an ISO-8601 query string into a ``datetime`` (or
  ``None``), raising a 400 on a malformed value. Accepts a bare date
  (``2026-07-01`` → midnight) and a full datetime.
- ``to_naive_utc`` / ``row_dt`` — normalise aware↔naive datetimes for
  comparison. SQLite stores datetimes naive (``DateTime(timezone=True)`` is a
  no-op there); comparing a naive row value against an aware query param raises
  ``TypeError``. Postgres (``timestamptz``) returns aware values, so these
  helpers are a safe no-op there. See ``app/api/v1/exports.py`` for the
  original in-depth rationale.
"""

from datetime import UTC, datetime

from fastapi import HTTPException, status


def parse_iso_dt(raw: str | None) -> datetime | None:
    """Parse an ISO-8601 datetime query param. Raises 400 on a bad value.

    Accepted forms include a bare date (``2026-07-01`` → midnight) and a full
    ``2026-07-01T00:00:00``. Naive datetimes are assumed UTC. ``None`` passes
    through (no filter applied).
    """
    if raw is None:
        return None
    try:
        # ``fromisoformat`` handles both "YYYY-MM-DD" and full datetimes; it
        # rejects empty strings and malformed values with ValueError.
        return datetime.fromisoformat(raw)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"非法时间格式: {raw}",
        ) from e


def to_naive_utc(dt: datetime | None) -> datetime | None:
    """Drop tzinfo (converting to UTC first) so comparisons against SQLite rows work.

    SQLite stores datetimes without timezone info, so a row's ``created_at``
    arrives as naive. Comparing that against an offset-aware query param raises
    ``TypeError``. Normalise the aware side to naive-UTC. ``None`` passes
    through. On Postgres (aware ``timestamptz``) this is still safe — it just
    strips the tzinfo after converting to UTC.
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def row_dt(value: datetime | None) -> datetime | None:
    """Normalise a row's stored datetime to naive-UTC for comparison.

    Mirrors ``to_naive_utc`` but is also a no-op when the value is already
    naive (the SQLite case). Used together: ``to_naive_utc(query_param)`` on
    one side, ``row_dt(row.created_at)`` on the other, so both sides are
    naive-UTC regardless of which DB engine is running.
    """
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value
