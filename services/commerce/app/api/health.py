from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.api.deps import DbSession

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness probe used by orchestration and CI smoke tests."""
    return {"status": "ok"}


@router.get("/health/ready")
def readiness(response: Response, db: DbSession) -> dict[str, object]:
    """Readiness probe: reports ``ready`` only when the database is reachable."""
    checks: dict[str, str] = {}
    healthy = True
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        healthy = False
        checks["database"] = f"error: {exc.__class__.__name__}"
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if healthy else "unavailable", "checks": checks}
