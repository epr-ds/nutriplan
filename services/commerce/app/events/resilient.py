"""A resilience wrapper so a bus outage never fails the originating order write (COM-109).

Publishing happens in the request path, *after* the order has already been committed. If the broker
is briefly unavailable we must not turn a successful order into a ``500``: this decorator logs the
failure and swallows it, trading strict delivery for availability. (A transactional outbox would be
the stronger, at-least-once alternative; it is deliberately out of scope for this story.)
"""

from __future__ import annotations

import logging

from app.domain.events import DomainEvent
from app.events.publisher import EventPublisher

logger = logging.getLogger(__name__)


class ResilientEventPublisher:
    """Wrap a publisher, logging and swallowing any transport error."""

    def __init__(self, inner: EventPublisher) -> None:
        self._inner = inner

    def publish(self, event: DomainEvent) -> None:
        try:
            self._inner.publish(event)
        except Exception:
            # Best-effort: the write already succeeded, so a broker hiccup must not fail the write.
            logger.exception("Failed to publish domain event %s", type(event).__name__)
