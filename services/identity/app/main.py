from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.jwks import router as jwks_router
from app.api.users import router as users_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.ratelimit import RateLimitMiddleware

app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(RateLimitMiddleware)
register_exception_handlers(app)

app.include_router(health_router)
app.include_router(jwks_router)
app.include_router(auth_router)
app.include_router(users_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"service": settings.app_name, "status": "running"}
