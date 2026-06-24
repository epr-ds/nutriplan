from fastapi import FastAPI

from app.api.analysis import router as analysis_router
from app.api.errors import register_exception_handlers
from app.api.health import router as health_router
from app.api.optimization import router as optimization_router
from app.api.recommendations import router as recommendations_router
from app.core.config import settings

app = FastAPI(title=settings.app_name, version="0.1.0")
register_exception_handlers(app)
app.include_router(health_router)
app.include_router(recommendations_router)
app.include_router(analysis_router)
app.include_router(optimization_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"service": settings.app_name, "status": "running"}
