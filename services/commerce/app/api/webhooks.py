"""Payment webhooks router (COM-206): async settlement confirm/fail -> order state."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Request, status

from app.api.deps import KitchenWebhookServiceDep, PaymentWebhookServiceDep
from app.api.schemas import KitchenWebhookAck, PaymentWebhookAck

router = APIRouter(tags=["Webhooks"])


@router.post(
    "/webhooks/payments",
    response_model=PaymentWebhookAck,
    status_code=status.HTTP_200_OK,
    summary="Provider payment webhook (async settlement)",
)
async def payment_webhook(
    request: Request,
    service: PaymentWebhookServiceDep,
    signature: Annotated[str | None, Header(alias="X-Webhook-Signature")] = None,
) -> PaymentWebhookAck:
    """Settle an order from a provider's asynchronous payment webhook (COM-206).

    Unlike every other route this is authenticated by the provider's **signature**, not a user
    bearer token: the *raw* request body is verified against ``X-Webhook-Signature`` before anything
    is read from it (a missing or mismatched signature is a ``400``). A verified
    ``payment.confirmed`` event confirms the referenced order (``pending -> confirmed``); a
    ``payment.failed`` event fails it (``pending -> cancelled``). Both are idempotent, so a
    redelivered event is a safe no-op. An event whose reference names no order is a ``404``.
    """
    payload = await request.body()
    order = service.process(payload=payload, signature=signature or "")
    return PaymentWebhookAck.from_order(order)


@router.post(
    "/webhooks/kitchen",
    response_model=KitchenWebhookAck,
    status_code=status.HTTP_200_OK,
    summary="Kitchen status webhook (fulfilment sync)",
)
async def kitchen_webhook(
    request: Request,
    service: KitchenWebhookServiceDep,
    signature: Annotated[str | None, Header(alias="X-Webhook-Signature")] = None,
) -> KitchenWebhookAck:
    """Advance an order's fulfilment state from a kitchen's status webhook (COM-303).

    Like the payment webhook this is authenticated by the kitchen's **signature**, not a user
    bearer token: the *raw* request body is verified against ``X-Webhook-Signature`` before
    anything is read from it (a missing or mismatched signature is a ``400``). A verified
    ``kitchen.preparing`` event advances the referenced order (``confirmed -> preparing``);
    ``kitchen.dispatched`` advances it (``preparing -> in_transit``). Both are idempotent, so a
    redelivered event is a safe no-op; an out-of-order report is a ``409`` and an event whose
    reference names no order is a ``404``.
    """
    payload = await request.body()
    order = service.process(payload=payload, signature=signature or "")
    return KitchenWebhookAck.from_order(order)
