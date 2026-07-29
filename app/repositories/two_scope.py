"""Two-scope config repository base.

A two-scope config table stores both platform-wide defaults
(``tenant_id IS NULL``) and per-tenant overrides (``tenant_id = <id>``) in one
table. Unlike :class:`~app.repositories.base.TenantScopedRepository`, the
``tenant_id`` column is *nullable*, so the read methods select by scope
explicitly rather than filtering every query by a required tenant.

Subclass contract:
  - The model MUST have a nullable ``tenant_id`` column (NULL = platform).
  - Override ``_active_filter`` to add an "active row" predicate (e.g.
    ``Model.is_active.is_(True)``); leave it ``None`` to disable filtering.

The companion :class:`~app.repositories.base.TenantScopedRepository` covers the
other repo pattern: a required ``tenant_id`` for business-data isolation. The
two are the Repository layer's complementary base classes.
"""

from sqlalchemy import ColumnElement, select

from app.repositories.base import BaseRepository, ModelT


class TwoScopeRepository(BaseRepository[ModelT]):
    """Repository for two-scope config tables (platform default + tenant override).

    Subclasses set ``model`` (as on :class:`BaseRepository`) and optionally
    override ``_active_filter``. The ``get_platform`` / ``get_for_tenant`` reads
    are provided here so the two-scope query logic lives in exactly one place;
    service-layer upserts / fallback chains stay on the subclasses (they carry
    real business deltas like crypto, audit fields, and env-level projection).
    """

    _active_filter: ColumnElement[bool] | None = None

    async def get_platform(self) -> ModelT | None:
        """The platform-wide config row (``tenant_id IS NULL``), if any.

        When ``_active_filter`` is set (e.g. ``Model.is_active.is_(True)``) it is
        appended so inactive rows are excluded.
        """
        stmt = select(self.model).where(self.model.tenant_id.is_(None))  # type: ignore[attr-defined]
        if self._active_filter is not None:
            stmt = stmt.where(self._active_filter)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_tenant(self, tenant_id: str) -> ModelT | None:
        """The tenant-level override row for ``tenant_id``, if any.

        Platform rows (NULL tenant_id) are excluded by the equality predicate.
        When ``_active_filter`` is set it is appended so inactive rows are
        excluded.
        """
        stmt = select(self.model).where(self.model.tenant_id == tenant_id)  # type: ignore[attr-defined]
        if self._active_filter is not None:
            stmt = stmt.where(self._active_filter)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
