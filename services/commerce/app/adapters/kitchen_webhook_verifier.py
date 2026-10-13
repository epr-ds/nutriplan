"""Verify + parse an inbound kitchen status webhook (COM-303).

A kitchen reports progress by POSTing a signed callback to ``/webhooks/kitchen``. This adapter
is the inbound counterpart to the payment provider's :meth:`parse_webhook` (COM-206): it verifies
an HMAC-SHA256 signature over the **raw** request body using a shared kitchen webhook secret
(constant-time compare, so a bad or absent signature is rejected with a
:class:`~app.domain.errors.WebhookVerificationError` -> 400 before any order is touched) and
normalises the JSON into a :class:`~app.domain.kitchen.KitchenWebhookEvent`. The HMAC is inlined
here (rather than reusing the payment provider) because a kitchen is a distinct integration with
its own secret and event vocabulary; sharing would couple two unrelated trust boundaries.
"""

from __future__ import annotations

import hashlib
import hmac
import json

from app.domain.errors import WebhookVerificationError
from app.domain.kitchen import KitchenEventType, KitchenWebhookEvent


class KitchenWebhookVerifier:
    """Verifies a kitchen webhook's signature and parses it into a domain event (COM-303)."""

    def __init__(self, webhook_secret: str = "") -> None:
        self._webhook_secret = webhook_secret

    def parse(self, payload: bytes, signature: str) -> KitchenWebhookEvent:
        expected = hmac.new(
            self._webhook_secret.encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature or ""):
            raise WebhookVerificationError("kitchen webhook signature does not match")
        try:
            body = json.loads(payload)
            event_type = KitchenEventType(body["type"])
            reference = body["data"]["reference"]
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise WebhookVerificationError("kitchen webhook payload is malformed") from exc
        if not isinstance(reference, str) or not reference:
            raise WebhookVerificationError("kitchen webhook is missing a reference")
        return KitchenWebhookEvent(type=event_type, reference=reference)
