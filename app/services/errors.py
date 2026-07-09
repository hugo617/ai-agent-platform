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
