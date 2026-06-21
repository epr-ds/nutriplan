from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness probe used by orchestration and CI smoke tests."""
    return {"status": "ok"}
