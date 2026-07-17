"""Service-layer exceptions used to map error conditions to HTTP status codes.

The API layer inspects the exception type (not the message string) to decide
whether a failure is a 404 (resource missing) or a 400 (business rule violation).
Keeping these as ``ValueError`` subclasses preserves backwards compatibility
with existing ``except ValueError`` handlers while giving the API layer a
reliable, locale-independent signal for status-code selection.
"""


class BizError(ValueError):
    """400 — a business-rule check failed (duplicate name, invalid status, …)."""


class NotFoundError(ValueError):
    """404 — the referenced user/resource does not exist (or is soft-deleted)."""


class ScopeError(BizError):
    """422 — a restricted API token's requested scopes don't survive the
    live intersection with the grantor's current permissions.

    Subclasses :class:`BizError` so existing ``except BizError`` / ``except
    ValueError`` callers keep working, but the dedicated exception handler in
    ``app.main`` maps it to 422 (Unprocessable Entity) rather than BizError's
    400 — the failure is a request-input problem (the requested scope set is
    empty after intersection), not a generic business-rule violation. The
    dedicated status makes it easy for the frontend to surface a precise toast
    ("请扩大 scope 范围或联系授予者") instead of a generic 400.
    """
