"""LLM config repository.

Extends :class:`~app.repositories.two_scope.TwoScopeRepository` (see
:doc:`ADR-0002 <../../docs/adr/0002-twoscope-config-repository>`): a row's
``tenant_id`` is *nullable* (NULL = platform-wide default, non-null = tenant
override), so the platform-vs-tenant scope selection lives in the base class's
``get_platform`` / ``get_for_tenant``. Only the active-row predicate is
LlmConfig-specific, set via the ``_active_filter`` hook.
"""

from app.models.llm_config import LlmConfig
from app.repositories.two_scope import TwoScopeRepository


class LlmConfigRepository(TwoScopeRepository[LlmConfig]):
    model = LlmConfig

    # Both scopes keep one active row (inactive rows are reserved for a future
    # soft-deactivate feature; today every row is active).
    _active_filter = LlmConfig.is_active.is_(True)
