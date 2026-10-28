from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.errors import register_exception_handlers
from app.api.gateway import ai_router, dietary_router, identity_router
from app.api.gateway import router as gateway_router
from app.api.health import router as health_router
from app.api.metrics import router as metrics_router
from app.api.webhooks import router as webhooks_router
from app.core.config import settings
from app.core.telemetry import TelemetryMiddleware, configure_logging
from app.db.provisioning import provision_commerce


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Apply the Commerce schema migrations before serving traffic (COM-903).
    provision_commerce()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
configure_logging()
register_exception_handlers(app)

# Telemetry is added last so it is the outermost middleware.
app.add_middleware(TelemetryMiddleware)

app.include_router(health_router)
app.include_router(metrics_router)
app.include_router(gateway_router)
app.include_router(dietary_router)
app.include_router(identity_router)
app.include_router(ai_router)
app.include_router(webhooks_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"service": settings.app_name, "status": "running"}
