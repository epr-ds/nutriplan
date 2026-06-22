from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.errors import register_exception_handlers
from app.api.health import router as health_router
from app.api.meal_plans import router as meal_plans_router
from app.api.recipes import router as recipes_router
from app.core.config import settings
from app.db.mongo import (
    ensure_meal_plans_collection,
    ensure_recipes_collection,
    get_db,
    recipes,
)
from app.db.seed import seed_recipes


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Install validators + indexes and seed the reference recipe catalog before serving traffic.
    db = get_db()
    ensure_meal_plans_collection(db)  # DPL-101
    ensure_recipes_collection(db)  # DPL-201
    seed_recipes(recipes(db))  # DPL-201 reference catalog
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
register_exception_handlers(app)
app.include_router(health_router)
app.include_router(meal_plans_router)
app.include_router(recipes_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"service": settings.app_name, "status": "running"}
