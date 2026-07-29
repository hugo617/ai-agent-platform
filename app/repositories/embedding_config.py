"""Embedding config repository.

Extends :class:`~app.repositories.two_scope.TwoScopeRepository`: a row's
``tenant_id`` is *nullable* (NULL = platform-wide default, non-null = tenant
override), so the platform-vs-tenant scope selection lives in the base class's
``get_platform`` / ``get_for_tenant``. Only the active-row predicate is
EmbeddingConfig-specific, set via the ``_active_filter`` hook.
"""

from app.models.embedding_config import EmbeddingConfig
from app.repositories.two_scope import TwoScopeRepository


class EmbeddingConfigRepository(TwoScopeRepository[EmbeddingConfig]):
    model = EmbeddingConfig

    # Both scopes keep one active row (inactive rows are reserved for a future
    # soft-deactivate feature; today every row is active).
    _active_filter = EmbeddingConfig.is_active.is_(True)
