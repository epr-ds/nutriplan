"""COM-808: backend accessibility support — order/payment status vocabularies for screen readers.

The accessibility pass on checkout/payment/order UI (COM-808) maps the backend's order and payment
status vocabulary onto non-color screen-reader cues. The backend half of that gate: the status
enums the wire carries must be semantic, closed vocabularies (never color-only or free-form strings)
that an a11y pass can map onto distinct cues.
"""

from __future__ import annotations

from app.domain.enums import OrderStatus
from app.domain.payment import PaymentStatus


def test_the_order_status_vocabulary_is_closed_and_semantic_for_a11y_cues() -> None:
    """COM-808: the order status vocabulary must be a closed set of semantic values."""
    values = {status.value for status in OrderStatus}
    for expected in ("pending", "confirmed", "preparing", "in_transit", "delivered", "cancelled"):
        assert expected in values, f"order status vocabulary is missing the a11y cue {expected}"


def test_the_payment_status_vocabulary_is_closed_and_semantic_for_a11y_cues() -> None:
    """COM-808: the payment status vocabulary must be a closed set of semantic values."""
    values = {status.value for status in PaymentStatus}
    for expected in ("succeeded", "failed", "pending"):
        assert expected in values, f"payment status vocabulary is missing the a11y cue {expected}"
