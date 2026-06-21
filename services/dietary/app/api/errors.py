"""Translate domain errors into HTTP responses, keeping the domain free of transport concerns.

A fuller RFC 7807 ``application/problem+json`` model is the subject of DPL-108; for now an invariant
violation surfaces as a ``422`` with a human-readable detail.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.domain.errors import DomainError

# 422 Unprocessable Content — kept as a literal to avoid Starlette's deprecated status constant.
_HTTP_422 = 422


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _handle_domain_error(_request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=_HTTP_422, content={"detail": str(exc)})
