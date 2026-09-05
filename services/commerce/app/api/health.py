from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.api.deps import DbSession, GroceryBreakersDep

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness probe used by orchestration and CI smoke tests."""
    return {"status": "ok"}


@router.get("/health/ready")
def readiness(response: Response, db: DbSession, breakers: GroceryBreakersDep) -> dict[str, object]:
    """Readiness probe: reports ``ready`` only when the database is reachable.

    It also reports each grocery provider's circuit-breaker state (COM-407), which is how breaker
    state becomes observable from outside the process. An open circuit deliberately does *not* make
    the service unready: the fan-out degrades by skipping that provider, so the service still
    serves traffic and only the database gates readiness.
    """
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
    return {
        "status": "ready" if healthy else "unavailable",
        "checks": checks,
        "groceryProviders": [
            {
                "id": snapshot.provider_id,
                "state": snapshot.state.value,
                "consecutiveFailures": snapshot.consecutive_failures,
                "secondsUntilRetry": round(snapshot.seconds_until_retry, 3),
            }
            for snapshot in breakers.snapshot()
        ],
    }
