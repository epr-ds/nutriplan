from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import enforce_rate_limit
from app.api.errors import register_exception_handlers
from app.api.health import router as health_router
from app.api.notifications import router as notifications_router
from app.api.preferences import router as preferences_router
from app.core.config import settings


def create_app() -> FastAPI:
    """Build the notification service application.

    The feed and preferences routers are mounted with the per-user rate-limit dependency
    (NTF-702); health and the root stay open so probes and load balancers are never throttled.
    CORS is applied only when an allow-list is configured, so the default posture is
    same-origin.
    """
    app = FastAPI(title=settings.app_name, version="0.1.0")

    register_exception_handlers(app)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    guarded = [Depends(enforce_rate_limit)]
    app.include_router(health_router)
    # Before the feed router: ``/notifications/preferences`` is a literal segment that the feed's
    # ``/notifications/{notification_id}/read`` parameter would otherwise be offered first refusal
    # on. FastAPI matches in registration order, so the specific route is registered first.
    app.include_router(preferences_router, dependencies=guarded)
    app.include_router(notifications_router, dependencies=guarded)

    @app.get("/")
    def root() -> dict[str, str]:
        return {"service": settings.app_name, "status": "running"}

    return app


app = create_app()
