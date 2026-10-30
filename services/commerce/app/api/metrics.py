from fastapi import APIRouter
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

router = APIRouter(tags=["observability"])


@router.get("/metrics")
def metrics() -> Response:
    """Prometheus text exposition, scraped by the monitoring stack (COM-906)."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
