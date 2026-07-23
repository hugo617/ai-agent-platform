"""Booking endpoints — tenant-scoped device-usage reservations (slice 01).

Slice 01 surface: ``GET /`` , ``GET /{id}``, ``POST /``, ``PUT /{id}``,
``POST /{id}/cancel``. There is deliberately **no** ``DELETE`` endpoint (D8 —
bookings are cancelled, not deleted; the row stays as the audit trail).

Reads are behind router-level ``require_permission("bookings", "read")`` for
now; slice 03 will move the read guard into the endpoint body so the HQ
panorama branch (super_admin / hq_staff) can be served without a tenant role
(same refactor devices.py went through in its slice 03).

Writes keep the router-level guard:
- POST → ``bookings:create`` (owner / admin)
- PUT → ``bookings:update`` (owner / admin)
- cancel → ``bookings:delete`` (owner / admin). Cancel is semantically a
  "delete" of the booking's active lifecycle, so it reuses the delete perm
  rather than introducing a bespoke ``bookings:cancel`` — matches how the
  plan's permission impact (§4.3) models it.

Cancel returns **204** (D9): it's a POST-to-a-sub-resource action that
transitions state, not a resource creation. It's also idempotent: re-cancelling
an already-cancelled booking is a no-op that still returns 204 (mirrors the
DELETE-idempotency convention device unbind uses).
"""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.core.database import get_db
from app.schemas.booking import BookingCreate, BookingRead, BookingUpdate
from app.services.booking_service import BookingService

router = APIRouter(prefix="/bookings", tags=["bookings"])


# -------------------------------------------------------------------- reads


@router.get("/", response_model=list[BookingRead])
async def list_bookings(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[BookingRead]:
    """List this tenant's bookings (slice 01 — within-store only).

    Slice 03 replaces the router-level read guard with an endpoint-body HQ
    branch (cross-tenant viewers → ``BookingHqRead`` panorama).
    """
    return await BookingService(db).list(
        user.user_id, user.tenant_id, platform_role=user.platform_role
    )


@router.get(
    "/{booking_id}",
    response_model=BookingRead,
    dependencies=[Depends(require_permission("bookings", "read"))],
)
async def get_booking(
    booking_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BookingRead:
    """Get one booking. A foreign tenant's id collapses to 404 (no
    enumeration leak)."""
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
