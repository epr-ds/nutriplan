from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.errors import register_exception_handlers
from app.api.favorites import router as favorites_router
from app.api.health import router as health_router
from app.api.meal_plans import router as meal_plans_router
from app.api.metrics import router as metrics_router
from app.api.nutrition import router as nutrition_router
from app.api.recipes import router as recipes_router
from app.core.config import settings
from app.core.telemetry import TelemetryMiddleware, configure_logging
from app.db.mongo import get_db
from app.db.provisioning import provision_dietary


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Install validators + indexes and seed the reference recipe catalog before serving traffic.
    provision_dietary(get_db())
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
configure_logging()
# Telemetry is added last so it is the outermost middleware: it observes responses produced by
# anything upstream (there is no rate limiter on this service yet) as well as the routes.
app.add_middleware(TelemetryMiddleware)
register_exception_handlers(app)
app.include_router(health_router)
app.include_router(metrics_router)
app.include_router(meal_plans_router)
app.include_router(recipes_router)
app.include_router(favorites_router)
app.include_router(nutrition_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"service": settings.app_name, "status": "running"}
