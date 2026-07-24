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


class InvalidTransition(BizError):
    """400 — a booking state-machine transition was refused.

    Raised by ``booking_state.transition`` when the ``(current_state, action)``
    pair is not one of the 6 legal edges (plan-device-poweron §0 D1/D2/D3).
    Subclasses :class:`BizError` purely for semantic clarity — the default
    ``BizError`` handler in ``app.main`` already maps subclasses to 400, so no
    new global handler is needed and the status code is unchanged (this is NOT
    the ``ScopeError`` pattern of registering a dedicated handler to override
    the status code). Subclassing lets unit tests ``pytest.raises(InvalidTransition)``
    for precise matching while every ``except BizError`` / ``except ValueError``
    caller keeps working.
    """

    def __init__(self, current: str, action: str) -> None:
        self.current = current
        self.action = action
        super().__init__(
            f"非法状态跳转:当前状态「{current}」不能执行动作「{action}」"
        )
