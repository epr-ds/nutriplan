"""API-layer dependency wiring.

The AI service sits behind the gateway, which performs full JWT verification at the edge
(JWKS, reused from P1 — AIA-804). This slice (AIA-201) only enforces that a Bearer token is
*present*: a request without one is rejected with ``401`` before any work is done. Verifying the
token's signature/claims here is intentionally out of scope and tracked by AIA-804.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)


def require_bearer(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    """Require a Bearer credential, returning the raw token or raising ``401``."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


BearerToken = Annotated[str, Depends(require_bearer)]
