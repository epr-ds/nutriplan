"""Commerce gateway: route ``/commerce/v1/*`` behind JWT verification (COM-902).

The commerce API is exposed through one gateway edge so the authenticated surface has a single
entry point: the gateway owns the ``/commerce/v1`` prefix and requires a verified caller JWT
(resolved via Identity's JWKS endpoint) on every routed operation, answering ``401`` at the edge
before any commerce handler runs.

Inbound provider callbacks (payment + kitchen webhooks) are HMAC-verified instead of JWT and stay
outside this gateway, as is the health probe.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api import fulfillment, orders, payment_methods
from app.api.deps import get_current_principal

router = APIRouter(prefix="/commerce/v1", dependencies=[Depends(get_current_principal)])

router.include_router(orders.router)
router.include_router(payment_methods.router)
router.include_router(fulfillment.router)
