from fastapi import APIRouter, Response, status

from app.core.config import settings
from app.core.readiness import evaluate_readiness

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness probe used by orchestration and CI smoke tests."""
    return {"status": "ok"}


@router.get("/health/ready")
def readiness(response: Response) -> dict[str, object]:
    """Readiness probe: 200 when the service can serve AI traffic, else 503.

    The body lists each dependency check so operators can see *why* the service is
    (not) ready without scraping logs.
    """
    result = evaluate_readiness(settings)
    if not result.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if result.ready else "not_ready",
        "checks": [
            {"name": check.name, "status": check.status, "detail": check.detail}
            for check in result.checks
        ],
    }
