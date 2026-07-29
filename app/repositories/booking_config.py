"""Booking-config repository.

Extends :class:`~app.repositories.two_scope.TwoScopeRepository` (see
:doc:`ADR-0002 <../../docs/adr/0002-twoscope-config-repository>`): a row's
``tenant_id`` is *nullable* (NULL = platform-wide default, non-null = tenant
override), so the platform-vs-tenant scope selection lives in the base class's
``get_platform`` / ``get_for_tenant``. ``_active_filter`` is left at its default
``None`` — ``BookingConfig`` has no ``is_active`` column, so no active-row
predicate is applied (the pre-migration behaviour: every row is visible).

Multi-tenant isolation note (plan §4.3): the tenant-scoped GET/PUT endpoints
pass ``tenant_id`` from the resolved caller (never the URL/body for store
roles — the API layer enforces that), so this repo is never asked for "another
tenant's" row by a store principal. A platform writer (super_admin) explicitly
reads/writes any tenant's override; that is the intended cross-tenant path.
"""

from app.models.booking_config import BookingConfig
from app.repositories.two_scope import TwoScopeRepository


class BookingConfigRepository(TwoScopeRepository[BookingConfig]):
    model = BookingConfig

    # No is_active column on BookingConfig — leave the hook at its default None
    # so the base class applies no active-row predicate.
