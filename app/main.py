"""FastAPI application entry point."""

import time
from contextlib import asynccontextmanager

import jwt
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import (
    agents,
    api_tokens,
    auth,
    billing,
    chat,
    conversations,
    customers,
    dashboard,
    exports,
    groups,
    knowledge,
    logs,
    members,
    notifications,
    permissions,
    roles,
    search,
    tenant_config,
    tenants,
    uploads,
    users,
)
from app.api.v1 import (
    settings as settings_router,
)
from app.core.config import settings
from app.core.database import get_db
from app.core.metrics import IN_PROGRESS, LATENCY, REQUESTS, render_metrics
from app.core.validation_errors import localize_message
from app.services.errors import BizError, NotFoundError

# Paths excluded from request metrics. The infra/observability endpoints would
# otherwise self-reference (every /metrics scrape inflates its own counter) and
# the liveness/readiness probes are too noisy to be useful as business signals.
_METRIC_EXEMPT_PATHS: frozenset[str] = frozenset(
    {"/metrics", "/health", "/ready", "/openapi.json", "/docs", "/redoc"}
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: warm the casbin enforcer so the first request isn't slow.
    # Lazy import keeps test startup fast when casbin isn't needed.
    from app.core.casbin_enforcer import get_enforcer

    try:
        get_enforcer()
    except Exception as e:  # noqa: BLE001 - don't crash startup; surface on first call
        app.state.casbin_error = str(e)

    # Periodic-job scheduler (priority 54). Idempotent + gated behind
    # SCHEDULER_ENABLED: disabled in tests (create_app is called per-test),
    # and a no-op if already running. See app/core/scheduler.py.
    from app.core.scheduler import init_scheduler, shutdown_scheduler

    init_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="多租户智能体云平台(FastAPI + pycasbin + LangGraph)",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --------------------------------------------------------------
    # Observability middleware: record request count + latency for the
    # Prometheus metrics endpoint. The route *template* is used as the
    # path label (e.g. "/api/v1/agents/{agent_id}", not the raw URL with
    # the id substituted in) to keep label cardinality bounded. Infra
    # endpoints (/metrics, /health, /ready, docs) are excluded so a
    # metrics scrape can't inflate its own counter.
    # --------------------------------------------------------------
    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        path = request.url.path
        exempt = path in _METRIC_EXEMPT_PATHS
        if exempt:
            return await call_next(request)

        IN_PROGRESS.inc()
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            elapsed = time.perf_counter() - start
            IN_PROGRESS.dec()
            # Prefer the matched route template (keeps cardinality bounded);
            # collapse unmatched routes (404) into a single "unmatched" label
            # rather than the raw path — otherwise a client hitting distinct
            # unknown URLs would create one label series per URL and exhaust
            # the Prometheus registry (cardinality bomb).
            route = request.scope.get("route")
            label_path = getattr(route, "path", None) or "unmatched"
            REQUESTS.labels(request.method, label_path, str(status_code)).inc()
            LATENCY.labels(request.method, label_path).observe(elapsed)

    # Register v1 routers under the API prefix.
    prefix = settings.api_v1_prefix
    app.include_router(auth.router, prefix=prefix)
    app.include_router(tenants.router, prefix=prefix)
    app.include_router(api_tokens.router, prefix=prefix)
    app.include_router(agents.router, prefix=prefix)
    app.include_router(users.router, prefix=prefix)
    app.include_router(members.router, prefix=prefix)
    app.include_router(roles.router, prefix=prefix)
    app.include_router(permissions.router, prefix=prefix)
    app.include_router(settings_router.router, prefix=prefix)
    app.include_router(chat.router, prefix=prefix)
    app.include_router(conversations.router, prefix=prefix)
    app.include_router(customers.router, prefix=prefix)
    app.include_router(groups.router, prefix=prefix)
    app.include_router(billing.router, prefix=prefix)
    app.include_router(dashboard.router, prefix=prefix)
    app.include_router(logs.router, prefix=prefix)
    app.include_router(search.router, prefix=prefix)
    app.include_router(tenant_config.router, prefix=prefix)
    app.include_router(notifications.router, prefix=prefix)
    app.include_router(exports.router, prefix=prefix)
    app.include_router(uploads.router, prefix=prefix)
    app.include_router(knowledge.router, prefix=prefix)

    async def _db_ping(db: AsyncSession) -> str:
        """Run ``SELECT 1`` against the configured DB. Returns 'ok'/'fail'.

        Used by both /health (liveness — must stay fast and never raise) and
        /ready (readiness — gates traffic). Any exception is treated as a
        failure; the caller decides the HTTP status. Uses the same session
        dependency as business endpoints, so test DB overrides apply.
        """
        try:
            await db.execute(text("SELECT 1"))
            return "ok"
        except Exception:  # noqa: BLE001 - probe must never raise
            return "fail"

    @app.get("/health", tags=["meta"])
    async def health(db: AsyncSession = Depends(get_db)) -> dict:
        """Liveness probe.

        Stays lightweight and always returns 200 while the process is up. The
        DB ping is best-effort (a transient DB blip should not restart the pod
        — that's /ready's job), surfaced as ``db`` but never changes the status
        code. Kept fast by the connection pool's ``pool_pre_ping``.
        """
        return {
            "status": "ok",
            "app": settings.app_name,
            "env": settings.app_env,
            "db": await _db_ping(db),
        }

    @app.get("/ready", tags=["meta"])
    async def ready(db: AsyncSession = Depends(get_db)) -> JSONResponse:
        """Readiness probe — gates traffic on real dependency health.

        Returns 200 when the DB is reachable, 503 otherwise. Unlike /health
        (liveness), a failing check here makes the orchestrator stop sending
        traffic until it recovers.
        """
        db_status = await _db_ping(db)
        ready = db_status == "ok"
        return JSONResponse(
            status_code=200 if ready else 503,
            content={
                "status": "ready" if ready else "not_ready",
                "checks": {"db": db_status},
            },
        )

    @app.get("/metrics", tags=["meta"])
    async def metrics() -> Response:
        """Prometheus exposition endpoint (text format)."""
        body, content_type = render_metrics()
        return Response(content=body, media_type=content_type)

    # ------------------------------------------------------------------
    # Dev-only helpers: JWKS endpoint + test-token minting.
    #
    # When LOGTO_ISSUER points at this backend (e.g.
    # ``http://localhost:8000/oidc``), the JWT verifier in security.py
    # fetches signing keys from ``/oidc/jwks`` below — so dev tokens minted
    # by ``/dev/token`` validate through the *exact same* code path as real
    # Logto tokens. This lets you log in to the frontend without configuring
    # Logto yet.
    #
    # Gated behind development mode; raises 404 in other envs.
    # ------------------------------------------------------------------

    @app.get("/oidc/jwks", tags=["dev"])
    async def jwks() -> Response:
        """Serve the dev public key as a JWKS document."""
        if settings.app_env != "development":
            return JSONResponse(status_code=404, content={"detail": "not found"})
        from app.core.dev_keys import jwks_json

        return Response(content=jwks_json(), media_type="application/json")

    @app.post("/dev/token", tags=["dev"])
    async def dev_token(payload: dict) -> dict:
        """Mint a short-lived dev JWT for local login.

        Body (all optional, defaults provided):
            {"sub": "dev-user", "tenant_id": "dev-tenant", "email": null, "platform_role": null}
        """
        if settings.app_env != "development":
            return JSONResponse(status_code=404, content={"detail": "not found"})
        from app.core.dev_keys import get_dev_keys

        keys = get_dev_keys()
        now = int(time.time())
        claims = {
            "sub": payload.get("sub", "dev-user"),
            "tenant_id": payload.get("tenant_id", "dev-tenant"),
            "email": payload.get("email"),
            "platform_role": payload.get("platform_role"),
            "iss": settings.logto_issuer,
            "aud": settings.logto_audience,
            "iat": now,
            "exp": now + 3600,
        }
        token = jwt.encode(claims, keys.private_pem, algorithm="RS256", headers={"kid": keys.kid})
        return {"access_token": token, "expires_in": 3600}

    @app.post("/dev/bootstrap", tags=["dev"])
    async def dev_bootstrap(payload: dict = None) -> dict:
        """Create a dev tenant + user + seed casbin policies for local login.

        Idempotent — safe to call repeatedly. After this, mint a token via
        ``/dev/token`` with the same ``sub`` / ``tenant_id`` and sign in.
        """
        if settings.app_env != "development":
            return JSONResponse(status_code=404, content={"detail": "not found"})

        from app.core.database import AsyncSessionLocal
        from app.schemas.tenant import TenantCreate
        from app.services.tenant_service import TenantService

        user_id = (payload or {}).get("sub", "dev-user")
        tenant_name = (payload or {}).get("tenant_name", "Development Tenant")

        async with AsyncSessionLocal() as db:
            svc = TenantService(db)
            tenants = await svc.list_user_tenants(user_id)
            if tenants:
                return {"tenant_id": tenants[0].id, "user_id": user_id, "exists": True}

            tenant = await svc.create_tenant(
                owner_user_id=user_id,
                payload=TenantCreate(name=tenant_name),
                owner_email=(payload or {}).get("email"),
            )
            return {"tenant_id": tenant.id, "user_id": user_id, "exists": False}

    @app.exception_handler(PermissionError)
    async def _permission_handler(request: Request, exc: PermissionError) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    # Service-layer business errors → 400/404 automatically. This lets the API
    # layer drop the ``try/except ValueError: raise _http_exc(e)`` boilerplate
    # (was duplicated across 10 router modules): a service ``raise BizError(...)``
    # or ``raise NotFoundError(...)`` now surfaces as the right HTTP status with
    # no per-endpoint handler code. Both are ValueError subclasses, so existing
    # ``except ValueError`` callers (if any) still work.
    @app.exception_handler(BizError)
    async def _biz_error_handler(request: Request, exc: BizError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(NotFoundError)
    async def _not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Replace each English Pydantic msg with a localized one, keeping the
        # native 422 shape ({detail:[{loc,msg,type,...}]}) so the frontend and
        # OpenAPI/Apifox contract are unchanged. Unknown types fall through to
        # the original msg via localize_message's passthrough.
        localized = [{**e, "msg": localize_message(e)} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": localized})

    return app


app = create_app()
