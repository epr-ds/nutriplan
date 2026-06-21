"""Translate domain errors into HTTP responses, keeping the domain free of transport concerns.

A fuller RFC 7807 ``application/problem+json`` model is the subject of DPL-108; for now an invariant
violation surfaces as a ``422`` and a missing/!owned plan as a ``404``, each with a readable detail.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.domain.errors import DomainError, IllegalStateTransitionError, MealPlanNotFoundError

# Kept as literals to avoid Starlette's deprecated status constants.
_HTTP_404 = 404
_HTTP_409 = 409
_HTTP_422 = 422


def register_exception_handlers(app: FastAPI) -> None:
    # The more specific handlers are registered too; Starlette resolves by walking the exception's
    # MRO, so each subclass maps to its own status even though all are DomainError (→ 422):
    #   MealPlanNotFoundError → 404, IllegalStateTransitionError → 409. An empty-plan activation has
    #   no dedicated handler, so it falls through to the generic 422.
    @app.exception_handler(MealPlanNotFoundError)
    async def _handle_not_found(_request: Request, exc: MealPlanNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=_HTTP_404, content={"detail": str(exc)})

    @app.exception_handler(IllegalStateTransitionError)
    async def _handle_illegal_transition(
        _request: Request, exc: IllegalStateTransitionError
    ) -> JSONResponse:
        return JSONResponse(status_code=_HTTP_409, content={"detail": str(exc)})

    @app.exception_handler(DomainError)
    async def _handle_domain_error(_request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=_HTTP_422, content={"detail": str(exc)})
