"""Booking endpoints — tenant-scoped device-usage reservations.

Reads (``GET /`` and ``GET /{booking_id}``) branch in the endpoint body on
the caller's platform role:
- **Cross-tenant viewers** (super_admin / hq_staff) → HQ panorama
  (``BookingHqRead`` across every tenant). No router-level read guard —
  ``hq_staff`` has no tenant role, so ``require_permission("bookings",
  "read")`` would 403 them before the branch. The actual bypass lives in
  ``permission_service.check`` (``hq_staff`` + ``read`` short-circuit +
  ``super_admin`` bypass), reached via the service's panorama path (which
  skips ``require`` entirely). Mirrors the devices.py slice-03 refactor.
- **Tenant roles** (owner / admin / member) → within-store ``BookingRead``,
  scoped to the caller's tenant. Permission is enforced inside
  ``BookingService.list / get`` (``require("bookings", "read")``); member
  passes because the default perms grant ``bookings:read``.

Writes (POST / PUT / cancel) keep the router-level
``require_permission("bookings", <act>)`` guard — hq_staff / super_admin
without a store role are correctly 403'd there (the HQ viewer is read-only).

There is deliberately **no** ``DELETE`` endpoint (D8 — bookings are
cancelled, not deleted; the row stays as the audit trail).

Cancel returns **204** (D9): it's a POST-to-a-sub-resource action that
transitions state, not a resource creation. It's also idempotent: re-cancelling
an already-cancelled booking is a no-op that still returns 204 (mirrors the
DELETE-idempotency convention device unbind uses).
"""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.core.database import get_db
from app.schemas.booking import (
    BookingCreate,
    BookingEndPayload,
    BookingHqRead,
    BookingRead,
    BookingUpdate,
)
from app.services.booking_service import BookingService

router = APIRouter(prefix="/bookings", tags=["bookings"])


# -------------------------------------------------------------------- reads
#
# ``response_model=None`` because the return shape branches on the caller's
# role: ``BookingRead`` for tenant roles, ``BookingHqRead`` (a subclass that
# adds ``tenant_name`` / ``device_name`` / ``customer_name``) for cross-tenant
# viewers. Declaring either as the response_model would either drop the
# panorama fields (``BookingRead``) or pollute the store view with three null
# ``*_name`` keys (``BookingHqRead``). ``response_model=None`` keeps each
# branch's shape honest; mirrors devices.py.


@router.get("/", response_model=None)
async def list_bookings(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[BookingRead] | list[BookingHqRead]:
    """List bookings.

    - super_admin / hq_staff → HQ panorama (``BookingHqRead``, every tenant).
    - owner / admin / member → this tenant's bookings (``BookingRead``).
    """
    return await BookingService(db).list(
        user.user_id, user.tenant_id, platform_role=user.platform_role
    )


@router.get("/{booking_id}", response_model=None)
async def get_booking(
    booking_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BookingRead | BookingHqRead:
    """Get one booking.

    - super_admin / hq_staff → HQ panorama (``BookingHqRead``, any tenant).
    - owner / admin / member → this tenant's booking (``BookingRead``); a
      foreign tenant's id collapses to 404 (no enumeration leak).
    """
    return await BookingService(db).get(
        user.user_id,
        user.tenant_id,
        booking_id,
        platform_role=user.platform_role,
    )


# ------------------------------------------------------------------- writes


@router.post(
    "/",
    response_model=BookingRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("bookings", "create"))],
)
async def create_booking(
    payload: BookingCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BookingRead:
    """Create a booking. New bookings always start ``pending``; ``status`` /
    ``started_at`` / ``ended_at`` / ``feedback`` are not on the create schema
    (status-guard rule). Time-slot conflicts → 400 (BizError, NOT 409)."""
    return await BookingService(db).create(
        user.user_id,
        user.tenant_id,
        payload,
        platform_role=user.platform_role,
    )


@router.put(
    "/{booking_id}",
    response_model=BookingRead,
    dependencies=[Depends(require_permission("bookings", "update"))],
)
async def update_booking(
    booking_id: str,
    payload: BookingUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BookingRead:
    """Reschedule / re-note a booking. Only ``pending`` bookings are mutable
    (D10); ``device_id`` is immutable. Time changes re-run the overlap check
    excluding self."""
    return await BookingService(db).update(
        user.user_id,
        user.tenant_id,
        booking_id,
        payload,
        platform_role=user.platform_role,
    )


# ----------------------------------------------------------- cancel (action)
#
# Cancel is a POST-to-a-sub-resource action: ``POST /bookings/{id}/cancel``.
# It returns **204, not 201** — no resource is created; an existing booking's
# status transitions pending → cancelled. Idempotent: re-cancelling an
# already-cancelled booking is a no-op that still returns 204 (mirrors the
# DELETE-idempotency convention device unbind uses — saves the client a
# GET-then-cancel round-trip).
#
# Guard: ``require_permission("bookings", "delete")``. Cancel is semantically
# the "delete" of a booking's active lifecycle, so it reuses the delete perm
# rather than introducing a bespoke ``bookings:cancel``.


@router.post(
    "/{booking_id}/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("bookings", "delete"))],
)
async def cancel_booking(
    booking_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Cancel a booking (pending → cancelled). Idempotent: an already-
    cancelled booking returns 204 with no write. Cancelling a booking in any
    other non-pending state → 400 (those states are owned by device-poweron's
    action endpoints)."""
    await BookingService(db).cancel(
        user.user_id,
        user.tenant_id,
        booking_id,
        platform_role=user.platform_role,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------ lifecycle actions
#
# device-poweron slice 01: ``start`` / ``end`` / ``no-show`` advance a booking
# through its active lifecycle. All three deliberately carry **NO**
# router-level ``require_permission`` dependency (plan §0 B1/D7/D8) — unlike
# ``create`` / ``update`` / ``cancel`` above, authorization is decided inside
# the function body. ``start`` is the reason: it serves BOTH a customer
# principal (who may carry no tenant role at all in production) and a store
# principal, and a router-level ``require_permission("bookings", "update")``
# would 403 the customer before the body could branch on
# ``user.customer_id``. ``end`` / ``no-show`` only serve store principals but
# follow the same shape for consistency (and so P-section permission tests
# mock the same way).
#
# Returns: ``start`` / ``end`` → 200 + ``BookingRead`` (the client reads back
# ``started_at`` / ``ended_at`` to refresh the UI); ``no-show`` → 204 no body
# (a pure status flip, mirroring ``/cancel``).


@router.post("/{booking_id}/start", response_model=BookingRead)
async def start_booking(
    booking_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BookingRead:
    """Start a booking (pending / confirmed → in_service), recording
    ``started_at``.

    Authorization is branched in the service on ``user.customer_id``:
    a customer principal (``customer_id`` set) must own the booking and may
    NOT start walk-in bookings; a store principal (``customer_id`` None)
    needs ``bookings:update`` (owner / admin, not member). See
    ``BookingService.start`` for the full matrix.
    """
    return await BookingService(db).start(
        user.user_id,
        user.tenant_id,
        booking_id,
        platform_role=user.platform_role,
        customer_id=user.customer_id,
    )


@router.post("/{booking_id}/end", response_model=BookingRead)
async def end_booking(
    booking_id: str,
    payload: BookingEndPayload | None = None,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BookingRead:
    """End a booking (in_service → done), recording ``ended_at`` and optional
    ``feedback``.

    Authorization: store owner only (``bookings:delete``) — admin / member /
    customer / hq_staff → 403. ``payload`` is optional; omitting it or
    sending ``feedback: null`` ends the booking without a service note.
    """
    return await BookingService(db).end(
        user.user_id,
        user.tenant_id,
        booking_id,
        platform_role=user.platform_role,
        payload=payload,
    )


@router.post(
    "/{booking_id}/no-show",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def no_show_booking(
    booking_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Mark a booking as no-show (pending / confirmed / in_service →
    no_show). Pure status flip — no timestamp recorded. Authorization: store
    owner only (``bookings:delete``). Returns 204 (mirrors ``/cancel``)."""
    await BookingService(db).no_show(
        user.user_id,
        user.tenant_id,
        booking_id,
        platform_role=user.platform_role,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
