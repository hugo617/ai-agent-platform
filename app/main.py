"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import agents, auth, chat, tenants
from app.core.config import settings


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
        description="Multi-tenant AI Agent SaaS platform",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register v1 routers under the API prefix.
    prefix = settings.api_v1_prefix
    app.include_router(auth.router, prefix=prefix)
    app.include_router(tenants.router, prefix=prefix)
    app.include_router(agents.router, prefix=prefix)
    app.include_router(chat.router, prefix=prefix)

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        return {"status": "ok", "app": settings.app_name}

    @app.exception_handler(PermissionError)
    async def _permission_handler(request: Request, exc: PermissionError) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    return app


app = create_app()
