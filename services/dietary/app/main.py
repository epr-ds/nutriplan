from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.config import settings
from app.db.mongo import ensure_meal_plans_collection, get_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Install the meal_plans validator + indexes before serving traffic (DPL-101).
    ensure_meal_plans_collection(get_db())
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.include_router(health_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"service": settings.app_name, "status": "running"}
