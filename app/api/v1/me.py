"""Customer-principal endpoints — the ``/me`` surface for customer identities.

Distinct from ``/auth/me`` (which is the *user* principal's profile surface):
``/me/bookings`` is keyed off ``current_user.customer_id`` and is the customer-
only view of their own reservations. Store-staff accounts (no ``customer_id``
claim) are rejected at the service layer (403) — staff read via ``/bookings/``.

Anti-override defence (plan §7 risk table, "customer own bypass"): the endpoint
deliberately takes NO ``customer_id`` query/body parameter. The id is injected
from the resolved principal, so a client cannot name another customer's id and
pull their bookings. A stray ``?customer_id=`` on the URL is simply never read.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user
from app.core.database import get_db
from app.schemas.booking import BookingRead
from app.services.booking_service import BookingService

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/bookings", response_model=list[BookingRead])
async def list_my_bookings(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[BookingRead]:
    """The calling customer's own bookings.

    ``customer_id`` is sourced from the resolved principal (``CurrentUser``),
    never from request input — this is the anti-override defence in the plan's
    risk table. Store-staff principals (``customer_id`` None) get 403 via
    ``BookingService.list_my_bookings``; this is a customer-only surface.

    Note the deliberate divergence from ``GET /bookings/``: there is NO
    router-level ``require_permission`` here. A customer principal may hold no
    tenant role at all, so authorization keys off ``customer_id`` presence
    (service layer → ``PermissionError`` → 403), not casbin — per plan §4.3.
    """
    return await BookingService(db).list_my_bookings(user.customer_id)
