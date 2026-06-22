"""RFC 7807 ``application/problem+json`` error responses (DPL-108).

Every 4xx/5xx response from the Dietary API is rendered as a *problem document* so clients get a
single, predictable error shape (``type``/``title``/``status`` plus an optional ``detail`` and
``instance``) instead of a grab-bag of ad-hoc bodies.

The domain layer stays transport-agnostic: it raises :class:`~app.domain.errors.DomainError`
subclasses and this module owns the mapping onto HTTP status codes — a missing/!owned plan → ``404``
(deliberately indistinguishable from "exists but isn't yours", to avoid enumeration), an illegal
lifecycle transition → ``409``, and any other invariant/precondition violation → ``422``. Framework
errors are covered too: auth/``HTTPException`` (``401``), request/query validation (``422`` with a
machine-readable ``errors`` array) and the catch-all ``500``.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.errors import DomainError, IllegalStateTransitionError, MealPlanNotFoundError

PROBLEM_JSON = "application/problem+json"

# Domain error -> HTTP status, most specific first (resolved by isinstance). Subclasses not listed
# here fall through to the generic 422, matching the rule that any unmapped invariant violation is
# an Unprocessable Entity.
_DOMAIN_STATUS: tuple[tuple[type[DomainError], int], ...] = (
    (MealPlanNotFoundError, HTTPStatus.NOT_FOUND),
    (IllegalStateTransitionError, HTTPStatus.CONFLICT),
    (DomainError, HTTPStatus.UNPROCESSABLE_ENTITY),
)


def _title(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:  # pragma: no cover - non-standard code
        return "Error"


def _status_for_domain_error(exc: DomainError) -> int:
    for error_type, status_code in _DOMAIN_STATUS:
        if isinstance(exc, error_type):
            return int(status_code)
    return int(HTTPStatus.UNPROCESSABLE_ENTITY)  # pragma: no cover - DomainError catch-all above


def problem_response(
    status_code: int,
    *,
    detail: str | None = None,
    instance: str | None = None,
    headers: dict[str, str] | None = None,
    **extra: Any,
) -> JSONResponse:
    """Build an RFC 7807 problem+json response (``type`` defaults to ``about:blank``)."""
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


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    return problem_response(
        _status_for_domain_error(exc), detail=str(exc), instance=request.url.path
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
    # A single DomainError handler catches every subclass (Starlette walks the MRO) and maps it via
    # the table above, so the status policy lives in one place.
    app.add_exception_handler(DomainError, domain_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
