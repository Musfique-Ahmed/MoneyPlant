"""FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    settings = get_settings()
    configure_logging(level=settings.log_level, redact=settings.log_redact_financial)
    logger.info("moneyplant.startup", extra={"event": "startup"})

    # Background data-source scheduler. A daemon thread, started only when
    # ``SYNC_SCHEDULER_ENABLED`` is true. Disabled in tests and whenever the
    # operator prefers the CLI / Windows Task Scheduler.
    scheduler = None
    if settings.sync_scheduler_enabled:
        from app.db.session import SessionLocal
        from app.services.sync.scheduler import SyncScheduler

        scheduler = SyncScheduler(
            SessionLocal,
            interval_seconds=settings.sync_scheduler_interval_seconds,
        )
        scheduler.start()
    app.state.sync_scheduler = scheduler

    yield

    if scheduler is not None:
        scheduler.stop()
    logger.info("moneyplant.shutdown", extra={"event": "shutdown"})


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="MoneyPlant API",
        version="0.1.0",
        description=(
            "SME financial decision copilot. "
            "All authoritative financial calculations are performed server-side. "
            "The LLM and Laya layers are advisory and cannot override hard rules."
        ),
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
        max_age=3600,
    )

    @app.get("/api/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok", "version": app.version}

    @app.get("/api/config/public", tags=["meta"])
    def public_config() -> dict[str, object]:
        """Public configuration flags. No secrets are ever returned."""
        return {
            "ai_modes": ["local", "openai", "anthropic"],
            "ai_default_mode": settings.ai_default_mode,
            "ai_local_model": settings.ai_local_model,
            "ai_local_base_url": settings.ai_local_base_url,
            "providers_configured": {
                "local": True,  # local endpoint availability checked at /api/ai/health
                "openai": settings.has_openai,
                "anthropic": settings.has_anthropic,
            },
            "laya_configured": settings.has_laya,
            "upload_max_bytes": settings.upload_max_bytes,
            "upload_allowed_extensions": list(settings.upload_allowed_extensions),
        }

    # Mount routers (each is added in its own phase).
    from app.api.ai import router as ai_router
    from app.api.alerts import router as alerts_router
    from app.api.businesses import router as businesses_router
    from app.api.data_sources import router as data_sources_router
    from app.api.decisions import router as decisions_router
    from app.api.financing import router as financing_router
    from app.api.imports import router as imports_router
    from app.api.insights import router as insights_router
    from app.api.scenarios import router as scenarios_router
    from app.api.transactions import router as transactions_router

    app.include_router(businesses_router, prefix="/api")
    app.include_router(imports_router, prefix="/api")
    app.include_router(transactions_router, prefix="/api")
    app.include_router(scenarios_router, prefix="/api")
    app.include_router(decisions_router, prefix="/api")
    app.include_router(ai_router, prefix="/api")
    app.include_router(alerts_router, prefix="/api")
    app.include_router(financing_router, prefix="/api")
    app.include_router(insights_router, prefix="/api")
    app.include_router(data_sources_router, prefix="/api")

    @app.exception_handler(Exception)
    async def unhandled(_request, exc: Exception) -> JSONResponse:
        # Never leak stack traces to the client. Log full detail server-side.
        logger.exception("moneyplant.unhandled", extra={"event": "unhandled"})
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "message": "An internal error occurred."},
        )

    return app


app = create_app()
