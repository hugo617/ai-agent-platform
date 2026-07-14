"""FastAPI application entry point."""

import time
from contextlib import asynccontextmanager

import jwt
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app.api.v1 import (
    agents,
    api_tokens,
    auth,
    billing,
    chat,
    conversations,
    customers,
    dashboard,
    groups,
    logs,
    members,
    permissions,
    roles,
    tenants,
    users,
)
from app.api.v1 import (
    settings as settings_router,
)
from app.core.config import settings
from app.core.validation_errors import localize_message


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: warm the casbin enforcer so the first request isn't slow.
    # Lazy import keeps test startup fast when casbin isn't needed.
    from app.core.casbin_enforcer import get_enforcer

    try:
        get_enforcer()
    except Exception as e:  # noqa: BLE001 - don't crash startup; surface on first call
        app.state.casbin_error = str(e)
    yield


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

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        return {"status": "ok", "app": settings.app_name, "env": settings.app_env}

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
