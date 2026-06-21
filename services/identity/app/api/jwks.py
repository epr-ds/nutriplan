from fastapi import APIRouter

from app.core import security

router = APIRouter(tags=["auth"])


@router.get("/.well-known/jwks.json")
def jwks() -> dict:
    """Public JSON Web Key Set used by other services to verify access tokens."""
    return security.build_jwks()
