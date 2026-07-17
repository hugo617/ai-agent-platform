"""Request-scoped API token context (contextvar).

This is the bridge that lets ``permission_service.check`` — including the ~60
direct callers across services + the LangGraph tool-internal checks — observe
the scopes of the ``ahp_`` API token that authenticated the current request,
WITHOUT changing any caller's signature.

Lifecycle per request
---------------------
1. ``deps._resolve_api_token`` resolves the ``ahp_`` token and, right before
   returning the ``CurrentUser``, calls ``current_token_ctx.set(TokenCtx(...))``
   on the host event-loop task.
2. FastAPI then runs the endpoint in the same task. For SSE endpoints the
   endpoint returns a ``StreamingResponse`` whose body generator is iterated
   by starlette in a child task spawned via ``anyio.create_task_group``
   (``start_soon`` → ``loop.create_task``). CPython's ``asyncio.create_task``
   snapshots the parent's contextvars context (``copy_context()``), so the
   child task — and therefore the LangGraph tool-internal ``check`` calls made
   inside it — sees the same ``current_token_ctx`` value.
3. ``permission_service.check`` reads ``current_token_ctx.get()`` at the very
   top: ``None`` means the JWT path (no API token) → skip the scope gate;
   otherwise enforce the restricted-scope intersection (see ``check``).

JWT path
--------
JWT requests never call ``_resolve_api_token`` and therefore never ``set`` the
contextvar — ``get()`` returns the default ``None`` and every existing test /
behaviour is unchanged (zero regression).

Why contextvar and not a ``check()`` signature change
-----------------------------------------------------
The alternative (add ``scopes: list[str] | None`` to ``check`` / ``require``)
would touch ~60 direct callers and still couldn't reach the LangGraph tools,
which only capture ``user_id`` / ``tenant_id`` via closure. A contextvar
reaches all of them for free.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass
class TokenCtx:
    """The scope context of the API token that authenticated the request.

    ``scope_mode == "full"``      → token inherits the grantor's full current
                                    permissions at check time (``check`` skips
                                    the scope gate; behaviour-equivalent to the
                                    pre-scope legacy tokens).
    ``scope_mode == "restricted"`` → only ``scopes`` (intersected live with the
                                     grantor's current permissions) are allowed.
    """

    token_id: str
    scopes: list[str]
    scope_mode: str  # "full" | "restricted"


# ``None`` = JWT path (or a test that didn't set it). Readers must treat ``None``
# as "no scope gate applies" — never as "deny everything".
current_token_ctx: ContextVar[TokenCtx | None] = ContextVar(
    "current_token_ctx", default=None
)
