"""Two-scope repository contract tests — LlmConfig four-state coverage.

These are repo-layer contract tests for the two-scope config pattern. They were
added BEFORE extracting the ``TwoScopeRepository`` base class (plan
twoscope-config slice 1) so that any silent drift in ``get_platform`` /
``get_for_tenant`` semantics — including the ``is_active`` filter — is caught at
the data-access layer rather than only via service/API tests.

The four states, per config repo:
  1. platform row exists (tenant_id IS NULL) -> get_platform returns it
  2. tenant row exists (tenant_id = X) -> get_for_tenant(X) returns it,
     get_for_tenant(Y) returns None
  3. no row at all -> both methods return None
  4. is_active filter: an is_active=False row is invisible (llm/embedding only)

Booking/embedding repos are migrated in slice 2; only LlmConfig is covered here.
"""

import pytest

from app.models.llm_config import LlmConfig
from app.repositories.llm_config import LlmConfigRepository


def _row(
    *,
    tenant_id: str | None,
    is_active: bool = True,
    default_model: str = "m",
) -> LlmConfig:
    """Build a minimal LlmConfig row for the two-scope contract tests."""
    return LlmConfig(
        tenant_id=tenant_id,
        api_key_encrypted="enc",
        api_key_hint="sk-***xxxx",
        base_url="https://example.com",
        default_model=default_model,
        available_models=[default_model],
        is_active=is_active,
    )


# --------------------------------------------------------------- state 1: platform row


@pytest.mark.asyncio
async def test_get_platform_returns_platform_row(db_session):
    """State 1: a platform row (tenant_id IS NULL) is returned by get_platform."""
    db_session.add(_row(tenant_id=None, default_model="platform-model"))
    await db_session.commit()

    repo = LlmConfigRepository(db_session)
    row = await repo.get_platform()

    assert row is not None
    assert row.tenant_id is None
    assert row.default_model == "platform-model"


# --------------------------------------------------------------- state 2: tenant row


@pytest.mark.asyncio
async def test_get_for_tenant_returns_own_row_and_not_others(
    db_session, tenant_owner
):
    """State 2: a tenant row is returned only for its own tenant_id."""
    tenant_id = tenant_owner["tenant_id"]
    db_session.add(_row(tenant_id=tenant_id, default_model="tenant-model"))
    await db_session.commit()

    repo = LlmConfigRepository(db_session)

    own = await repo.get_for_tenant(tenant_id)
    assert own is not None
    assert own.tenant_id == tenant_id
    assert own.default_model == "tenant-model"

    # A different tenant sees nothing (platform row excluded by equality).
    other = await repo.get_for_tenant("tnt-does-not-exist")
    assert other is None


# --------------------------------------------------------------- state 3: no row


@pytest.mark.asyncio
async def test_no_row_returns_none_for_both_methods(db_session, tenant_owner):
    """State 3: with no rows at all, both reads return None."""
    repo = LlmConfigRepository(db_session)

    assert await repo.get_platform() is None
    assert await repo.get_for_tenant(tenant_owner["tenant_id"]) is None


# --------------------------------------------------------------- state 4: is_active filter


@pytest.mark.asyncio
async def test_inactive_rows_are_filtered_out(db_session, tenant_owner):
    """State 4: is_active=False rows are invisible via the _active_filter hook.

    Seeds an inactive platform row AND an inactive tenant row, then asserts both
    reads return None — proving the is_active predicate is applied to both the
    platform and tenant scope queries.
    """
    db_session.add(_row(tenant_id=None, is_active=False, default_model="p-inactive"))
    db_session.add(
        _row(
            tenant_id=tenant_owner["tenant_id"],
            is_active=False,
            default_model="t-inactive",
        )
    )
    await db_session.commit()

    repo = LlmConfigRepository(db_session)

    assert await repo.get_platform() is None
    assert await repo.get_for_tenant(tenant_owner["tenant_id"]) is None
