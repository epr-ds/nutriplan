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

The ``/ai`` edge relays a verified caller to the AI service on the same bearer token
(AIA-804): the gateway owns the ``/ai`` prefix, requires a verified caller JWT at the edge,
and forwards the request, enforcing a per-user rate limit to protect cost before proxying.

The ``/notifications`` edge relays a verified caller to the Notification service on the same
bearer token (NTF-802): the gateway owns the versioned ``/notifications/v1`` prefix, requires a
verified caller JWT at the edge, and forwards the request (method, path, body, bearer) to the
Notification service, relaying its response back.
"""

from __future__ import annotations

from typing import Annotated, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api import fulfillment, orders, payment_methods
from app.api.deps import (
    SlidingWindowRateLimiter,
    get_ai_client,
    get_ai_rate_limiter,
    get_bearer_token,
    get_current_principal,
    get_dietary_client,
    get_identity_client,
    get_notification_client,
    optional_current_principal,
)
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
async def dietary_proxy(
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
    token: Annotated[str, Depends(get_bearer_token)],
    client: Annotated[httpx.Client, Depends(get_dietary_client)],
) -> Response:
    """Relay a verified caller to the Dietary service on the same bearer token (DPL-802)."""
    _ = principal  # JWT validity is enforced by the dependency above; relayed via the token.
    headers = {"Authorization": f"Bearer {token}"}
    body = await request.body()
    if request.method in {"POST", "PUT", "PATCH"} and body:
        content_type = request.headers.get("content-type")
        if content_type:
            headers["Content-Type"] = content_type
    url = request.url.path
    prefix = dietary_router.prefix or ""
    if url.startswith(prefix) and len(url) > len(prefix):
        url = url[len(prefix) :]
    # The Dietary service owns the unversioned resource namespaces (``/meal-plans``, ``/recipes``,
    # ...); the gateway owns the versioned ``/dietary/v1`` prefix, so drop the version segment
    # before forwarding to the service (mirrors the AI edge).
    version_prefix = "/v1"
    if url.startswith(version_prefix) and len(url) > len(version_prefix):
        url = url[len(version_prefix) :]
    if request.url.query:
        url = f"{url}?{request.url.query}"
    forward_url = f"/{url.lstrip('/')}" if url else url
    try:
        upstream = client.request(
            method=request.method,
            url=forward_url,
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


identity_router = APIRouter(prefix="/identity/v1")


@identity_router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def identity_proxy(
    request: Request,
    principal: Annotated[Optional[Principal], Depends(optional_current_principal)],
    client: Annotated[httpx.Client, Depends(get_identity_client)],
) -> Response:
    """Relay a verified caller to the Identity service on the same bearer token (IDN-802).

    The auth endpoints (``/auth/*``) are public: a caller reaches them before any token exists, so
    an anonymous principal is allowed through and the bearer token is forwarded as-is when
    present. Every other identity path requires a verified caller.
    """
    url = request.url.path
    prefix = identity_router.prefix or ""
    if url.startswith(prefix) and len(url) > len(prefix):
        url = url[len(prefix) :]
    if request.url.query:
        url = f"{url}?{request.url.query}"
    token = request.headers.get("Authorization")
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = token
    body = await request.body()
    if request.method in {"POST", "PUT", "PATCH"} and body:
        content_type = request.headers.get("content-type")
        if content_type:
            headers["Content-Type"] = content_type
    if principal is None and not url.startswith("/auth"):
        raise HTTPException(status_code=401, detail="Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    try:
        upstream = client.request(
            method=request.method,
            url=url,
            headers=headers,
            content=body or None,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Identity service unavailable") from exc
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


ai_router = APIRouter(prefix="/ai/v1")


@ai_router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def ai_proxy(
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
    token: Annotated[str, Depends(get_bearer_token)],
    client: Annotated[httpx.Client, Depends(get_ai_client)],
    limiter: Annotated[SlidingWindowRateLimiter, Depends(get_ai_rate_limiter)],
) -> Response:
    """Relay a verified caller to the AI service on the same bearer token (AIA-804)."""
    if not limiter.allow(principal.user_id):
        raise HTTPException(status_code=429, detail="AI rate limit exceeded")
    _ = principal  # JWT validity is enforced by the dependency above; relayed via the token.
    headers = {"Authorization": f"Bearer {token}"}
    body = await request.body()
    if request.method in {"POST", "PUT", "PATCH"} and body:
        content_type = request.headers.get("content-type")
        if content_type:
            headers["Content-Type"] = content_type
    url = request.url.path
    if request.url.query:
        url = f"{url}?{request.url.query}"
    # The AI service owns the ``/ai/<operation>`` namespace; the gateway owns the versioned
    # ``/ai/v1`` prefix, so drop the version segment before forwarding to the service.
    if url.startswith(ai_router.prefix or "") and len(url) > len(ai_router.prefix or ""):
        url = url[len(ai_router.prefix) :]
    forward_url = f"/ai/{url.lstrip('/')}" if url else url
    try:
        upstream = client.request(
            method=request.method,
            url=forward_url,
            headers=headers,
            content=body or None,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="AI service unavailable") from exc
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


notifications_router = APIRouter(prefix="/notifications/v1")


@notifications_router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def notifications_proxy(
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
    token: Annotated[str, Depends(get_bearer_token)],
    client: Annotated[httpx.Client, Depends(get_notification_client)],
) -> Response:
    """Relay a verified caller to the Notification service on the same bearer token (NTF-802).

    The Notification service owns the unversioned ``/notifications`` resource namespaces (feed,
    unread badge, per-notification read, preferences, push-device registration); the gateway owns
    the versioned ``/notifications/v1`` prefix, so the version segment is dropped before
    forwarding -- exactly like the AI and Dietary edges.
    """
    _ = principal  # JWT validity is enforced by the dependency above; relayed via the token.
    headers = {"Authorization": f"Bearer {token}"}
    body = await request.body()
    if request.method in {"POST", "PUT", "PATCH"} and body:
        content_type = request.headers.get("content-type")
        if content_type:
            headers["Content-Type"] = content_type
    url = request.url.path
    prefix = notifications_router.prefix or ""
    if url.startswith(prefix) and len(url) > len(prefix):
        url = url[len(prefix) :]
    if request.url.query:
        url = f"{url}?{request.url.query}"
    forward_url = f"/{url.lstrip('/')}" if url else url
    try:
        upstream = client.request(
            method=request.method,
            url=forward_url,
            headers=headers,
            content=body or None,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Notification service unavailable") from exc
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
