"""Two-scope repository contract tests — three repo, four-state (and three-state) coverage.

These are repo-layer contract tests for the two-scope config pattern. They were
added BEFORE extracting the ``TwoScopeRepository`` base class (plan
twoscope-config slice 1 + slice 2) so that any silent drift in ``get_platform``
/ ``get_for_tenant`` semantics — including the ``is_active`` filter — is caught
at the data-access layer rather than only via service/API tests.

The four states, per config repo:
  1. platform row exists (tenant_id IS NULL) -> get_platform returns it
  2. tenant row exists (tenant_id = X) -> get_for_tenant(X) returns it,
     get_for_tenant(Y) returns None
  3. no row at all -> both methods return None
  4. is_active filter: an is_active=False row is invisible (llm/embedding only)

Booking has no ``is_active`` column, so its contract is three states; the test
also confirms the "no filter" semantics (state 4 N/A: every row is visible) by
asserting a seeded row is returned without any active predicate.

Layout:
  - LlmConfig four states (slice 1).
  - EmbeddingConfig four states (slice 2).
  - BookingConfig three states + no-filter check (slice 2).
"""

import pytest

from app.models.booking_config import BookingConfig
from app.models.embedding_config import EmbeddingConfig
from app.models.llm_config import LlmConfig
from app.repositories.booking_config import BookingConfigRepository
from app.repositories.embedding_config import EmbeddingConfigRepository
from app.repositories.llm_config import LlmConfigRepository

# ============================================================================
# Row builders — one per model, minimal fields to satisfy NOT NULL columns.
# ============================================================================


def _llm_row(
    *,
    tenant_id: str | None,
    is_active: bool = True,
    default_model: str = "m",
) -> LlmConfig:
    return LlmConfig(
        tenant_id=tenant_id,
        api_key_encrypted="enc",
        api_key_hint="sk-***xxxx",
        base_url="https://example.com",
        default_model=default_model,
        available_models=[default_model],
        is_active=is_active,
    )


def _embedding_row(
    *,
    tenant_id: str | None,
    is_active: bool = True,
    model: str = "embed-m",
) -> EmbeddingConfig:
    return EmbeddingConfig(
        tenant_id=tenant_id,
        api_key_encrypted="enc",
        api_key_hint="sk-***xxxx",
        base_url="https://example.com",
        model=model,
        is_active=is_active,
    )


def _booking_row(
    *,
    tenant_id: str | None,
    default_duration_minutes: int = 45,
) -> BookingConfig:
    return BookingConfig(
        tenant_id=tenant_id,
        default_duration_minutes=default_duration_minutes,
        window_start="08:00",
        window_end="22:00",
    )


# ============================================================================
# LlmConfig four states (slice 1).
# ============================================================================


@pytest.mark.asyncio
async def test_llm_get_platform_returns_platform_row(db_session):
    """State 1: a platform row (tenant_id IS NULL) is returned by get_platform."""
    db_session.add(_llm_row(tenant_id=None, default_model="platform-model"))
    await db_session.commit()

    repo = LlmConfigRepository(db_session)
    row = await repo.get_platform()

    assert row is not None
    assert row.tenant_id is None
    assert row.default_model == "platform-model"


@pytest.mark.asyncio
async def test_llm_get_for_tenant_returns_own_row_and_not_others(
    db_session, tenant_owner
):
    """State 2: a tenant row is returned only for its own tenant_id."""
    tenant_id = tenant_owner["tenant_id"]
    db_session.add(_llm_row(tenant_id=tenant_id, default_model="tenant-model"))
    await db_session.commit()

    repo = LlmConfigRepository(db_session)

    own = await repo.get_for_tenant(tenant_id)
    assert own is not None
    assert own.tenant_id == tenant_id
    assert own.default_model == "tenant-model"

    other = await repo.get_for_tenant("tnt-does-not-exist")
    assert other is None


@pytest.mark.asyncio
async def test_llm_no_row_returns_none_for_both_methods(db_session, tenant_owner):
    """State 3: with no rows at all, both reads return None."""
    repo = LlmConfigRepository(db_session)

    assert await repo.get_platform() is None
    assert await repo.get_for_tenant(tenant_owner["tenant_id"]) is None


@pytest.mark.asyncio
async def test_llm_inactive_rows_are_filtered_out(db_session, tenant_owner):
    """State 4: is_active=False rows are invisible via the _active_filter hook.

    Seeds an inactive platform row AND an inactive tenant row, then asserts both
    reads return None — proving the is_active predicate is applied to both the
    platform and tenant scope queries.
    """
    db_session.add(_llm_row(tenant_id=None, is_active=False, default_model="p-inactive"))
    db_session.add(
        _llm_row(
            tenant_id=tenant_owner["tenant_id"],
            is_active=False,
            default_model="t-inactive",
        )
    )
    await db_session.commit()

    repo = LlmConfigRepository(db_session)

    assert await repo.get_platform() is None
    assert await repo.get_for_tenant(tenant_owner["tenant_id"]) is None


# ============================================================================
# EmbeddingConfig four states (slice 2).
# ============================================================================


@pytest.mark.asyncio
async def test_embedding_get_platform_returns_platform_row(db_session):
    """State 1: a platform row (tenant_id IS NULL) is returned by get_platform."""
    db_session.add(_embedding_row(tenant_id=None, model="platform-embed"))
    await db_session.commit()

    repo = EmbeddingConfigRepository(db_session)
    row = await repo.get_platform()

    assert row is not None
    assert row.tenant_id is None
    assert row.model == "platform-embed"


@pytest.mark.asyncio
async def test_embedding_get_for_tenant_returns_own_row_and_not_others(
    db_session, tenant_owner
):
    """State 2: a tenant row is returned only for its own tenant_id."""
    tenant_id = tenant_owner["tenant_id"]
    db_session.add(_embedding_row(tenant_id=tenant_id, model="tenant-embed"))
    await db_session.commit()

    repo = EmbeddingConfigRepository(db_session)

    own = await repo.get_for_tenant(tenant_id)
    assert own is not None
    assert own.tenant_id == tenant_id
    assert own.model == "tenant-embed"

    other = await repo.get_for_tenant("tnt-does-not-exist")
    assert other is None


@pytest.mark.asyncio
async def test_embedding_no_row_returns_none_for_both_methods(
    db_session, tenant_owner
):
    """State 3: with no rows at all, both reads return None."""
    repo = EmbeddingConfigRepository(db_session)

    assert await repo.get_platform() is None
    assert await repo.get_for_tenant(tenant_owner["tenant_id"]) is None


@pytest.mark.asyncio
async def test_embedding_inactive_rows_are_filtered_out(db_session, tenant_owner):
    """State 4: is_active=False rows are invisible via the _active_filter hook.

    Seeds an inactive platform row AND an inactive tenant row, then asserts both
    reads return None — proving the is_active predicate is applied to both the
    platform and tenant scope queries (matching the pre-migration behaviour).
    """
    db_session.add(
        _embedding_row(tenant_id=None, is_active=False, model="p-inactive")
    )
    db_session.add(
        _embedding_row(
            tenant_id=tenant_owner["tenant_id"], is_active=False, model="t-inactive"
        )
    )
    await db_session.commit()

    repo = EmbeddingConfigRepository(db_session)

    assert await repo.get_platform() is None
    assert await repo.get_for_tenant(tenant_owner["tenant_id"]) is None


# ============================================================================
# BookingConfig three states (slice 2) — no is_active column.
# ============================================================================


@pytest.mark.asyncio
async def test_booking_get_platform_returns_platform_row(db_session):
    """State 1: a platform row (tenant_id IS NULL) is returned by get_platform."""
    db_session.add(_booking_row(tenant_id=None, default_duration_minutes=60))
    await db_session.commit()

    repo = BookingConfigRepository(db_session)
    row = await repo.get_platform()

    assert row is not None
    assert row.tenant_id is None
    assert row.default_duration_minutes == 60


@pytest.mark.asyncio
async def test_booking_get_for_tenant_returns_own_row_and_not_others(
    db_session, tenant_owner
):
    """State 2: a tenant row is returned only for its own tenant_id."""
    tenant_id = tenant_owner["tenant_id"]
    db_session.add(_booking_row(tenant_id=tenant_id, default_duration_minutes=30))
    await db_session.commit()

    repo = BookingConfigRepository(db_session)

    own = await repo.get_for_tenant(tenant_id)
    assert own is not None
    assert own.tenant_id == tenant_id
    assert own.default_duration_minutes == 30

    other = await repo.get_for_tenant("tnt-does-not-exist")
    assert other is None


@pytest.mark.asyncio
async def test_booking_no_row_returns_none_for_both_methods(
    db_session, tenant_owner
):
    """State 3: with no rows at all, both reads return None."""
    repo = BookingConfigRepository(db_session)

    assert await repo.get_platform() is None
    assert await repo.get_for_tenant(tenant_owner["tenant_id"]) is None


@pytest.mark.asyncio
async def test_booking_no_active_filter_all_rows_visible(db_session, tenant_owner):
    """State 4 N/A: booking has no is_active column, so _active_filter is None.

    Seeds one platform + one tenant row and asserts BOTH are returned — proving
    the base class applies NO active predicate when ``_active_filter`` is None
    (the pre-migration behaviour where booking rows were never filtered).
    """
    db_session.add(_booking_row(tenant_id=None, default_duration_minutes=45))
    db_session.add(
        _booking_row(
            tenant_id=tenant_owner["tenant_id"], default_duration_minutes=60
        )
    )
    await db_session.commit()

    repo = BookingConfigRepository(db_session)

    platform = await repo.get_platform()
    assert platform is not None
    assert platform.tenant_id is None

    tenant = await repo.get_for_tenant(tenant_owner["tenant_id"])
    assert tenant is not None
    assert tenant.tenant_id == tenant_owner["tenant_id"]
