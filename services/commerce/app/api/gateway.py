"""Commerce gateway: route ``/commerce/v1/*`` behind JWT verification (COM-902).

The commerce API is exposed through one gateway edge so the authenticated surface has a single
entry point: the gateway owns the ``/commerce/v1`` prefix and requires a verified caller JWT
(resolved via Identity's JWKS endpoint) on every routed operation, answering ``401`` at the edge
before any commerce handler runs.

The ``/dietary`` edge relays a verified caller to the Dietary service on the same bearer token
(DPL-802): the gateway owns the ``/dietary`` prefix, requires a verified caller JWT at the edge,
and forwards the request (method, path, body, bearer) to the Dietary service, relaying its
response back. Inbound provider callbacks (payment + kitchen webhooks) are HMAC-verified instead of
JWT and stay outside this gateway, as is the health probe.
"""

from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api import fulfillment, orders, payment_methods
from app.api.deps import get_bearer_token, get_current_principal, get_dietary_client
from app.core.principal import Principal

router = APIRouter(prefix="/commerce/v1", dependencies=[Depends(get_current_principal)])

router.include_router(orders.router)
router.include_router(payment_methods.router)
router.include_router(fulfillment.router)

dietary_router = APIRouter(prefix="/dietary")


@dietary_router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
def dietary_proxy(
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
    token: Annotated[str, Depends(get_bearer_token)],
    client: Annotated[httpx.Client, Depends(get_dietary_client)],
) -> Response:
    """Relay a verified caller to the Dietary service on the same bearer token (DPL-802)."""
    _ = principal  # JWT validity is enforced by the dependency above; relayed via the token.
    headers = {"Authorization": f"Bearer {token}"}
    body = request.body()
    if request.method in {"POST", "PUT", "PATCH"} and body:
        content_type = request.headers.get("content-type")
        if content_type:
            headers["Content-Type"] = content_type
    url = request.url.path
    prefix = dietary_router.prefix or ""
    if url.startswith(prefix) and len(url) > len(prefix):
        url = url[len(prefix) :]
    if request.url.query:
        url = f"{url}?{request.url.query}"
    try:
        upstream = client.request(
            method=request.method,
            url=url,
            headers=headers,
            content=body or None,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Dietary service unavailable") from exc
    response_headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower()
        not in {
            "connection",
            "keep-alive",
            "proxy-authenticate",
            "proxy-authorization",
            "te",
            "trailer",
            "transfer-encoding",
            "upgrade",
        }
    }
    return Response(
        content=upstream.content, status_code=upstream.status_code, headers=response_headers
    )
