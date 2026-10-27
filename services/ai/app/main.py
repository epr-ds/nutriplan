from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.analysis import router as analysis_router
from app.api.deps import enforce_rate_limit
from app.api.errors import register_exception_handlers
from app.api.health import router as health_router
from app.api.metrics import router as metrics_router
from app.api.optimization import router as optimization_router
from app.api.recommendations import router as recommendations_router
from app.core.config import settings
from app.core.telemetry import TelemetryMiddleware, configure_logging


def create_app() -> FastAPI:
    """Build the AI service application.

    Every data router is mounted with the per-user rate-limit dependency (AIA-804); health
    and the root stay open so probes and load balancers are never throttled. CORS is applied
    only when an allow-list is configured, so the default posture is same-origin.

    Telemetry (AIA-806) is mounted last so it is the outermost middleware and observes the
    responses produced by the rate limiter (e.g. 429s) as well as the routes.
    """
    app = FastAPI(title=settings.app_name, version="0.1.0")
    configure_logging()
    register_exception_handlers(app)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.add_middleware(TelemetryMiddleware)

    guarded = [Depends(enforce_rate_limit)]
    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(recommendations_router, dependencies=guarded)
    app.include_router(analysis_router, dependencies=guarded)
    app.include_router(optimization_router, dependencies=guarded)

    @app.get("/")
    def root() -> dict[str, str]:
        return {"service": settings.app_name, "status": "running"}

    return app


app = create_app()
