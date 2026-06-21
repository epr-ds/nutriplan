"""RFC 7807 ``application/problem+json`` error responses (IDN-106).

All 4xx/5xx responses are rendered as problem documents so clients get a single,
predictable error shape across the Identity API.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_JSON = "application/problem+json"


def _title(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:  # pragma: no cover - non-standard code
        return "Error"


def problem_response(
    status_code: int,
    *,
    detail: str | None = None,
    instance: str | None = None,
    headers: dict[str, str] | None = None,
    **extra: Any,
) -> JSONResponse:
    """Build an RFC 7807 problem+json response."""
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": _title(status_code),
        "status": status_code,
    }
    if detail:
        body["detail"] = detail
    if instance:
        body["instance"] = instance
    body.update(extra)
    return JSONResponse(
        status_code=status_code, content=body, media_type=PROBLEM_JSON, headers=headers
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else None
    return problem_response(
        exc.status_code,
        detail=detail,
        instance=request.url.path,
        headers=getattr(exc, "headers", None),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = [
        {"loc": list(err.get("loc", [])), "msg": err.get("msg"), "type": err.get("type")}
        for err in exc.errors()
    ]
    return problem_response(
        HTTPStatus.UNPROCESSABLE_ENTITY,
        detail="Request validation failed",
        instance=request.url.path,
        errors=errors,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return problem_response(
        HTTPStatus.INTERNAL_SERVER_ERROR,
        detail="An unexpected error occurred",
        instance=request.url.path,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
