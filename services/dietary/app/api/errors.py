"""Translate domain errors into HTTP responses, keeping the domain free of transport concerns.

A fuller RFC 7807 ``application/problem+json`` model is the subject of DPL-108; for now an invariant
violation surfaces as a ``422`` and a missing/!owned plan as a ``404``, each with a readable detail.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.domain.errors import DomainError, MealPlanNotFoundError

# Kept as literals to avoid Starlette's deprecated status constants.
_HTTP_404 = 404
_HTTP_422 = 422


def register_exception_handlers(app: FastAPI) -> None:
    # The more specific handler is registered too; Starlette resolves by walking the exception's
    # MRO, so MealPlanNotFoundError maps to 404 even though it is also a DomainError (→ 422).
    @app.exception_handler(MealPlanNotFoundError)
    async def _handle_not_found(_request: Request, exc: MealPlanNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=_HTTP_404, content={"detail": str(exc)})

    @app.exception_handler(DomainError)
    async def _handle_domain_error(_request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=_HTTP_422, content={"detail": str(exc)})
