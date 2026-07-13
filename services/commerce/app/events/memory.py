"""An in-process :class:`~app.events.publisher.EventPublisher` for dev, CI, and tests (COM-109).

It simply retains every published event in order, so a single-replica dev/CI run works without a
broker and tests can assert exactly what was published. Production points ``COMMERCE_EVENT_BUS_URL``
at Redis instead (see :mod:`app.events.factory`); every layer above depends only on the port, so
swapping the two changes nothing else.
"""

from __future__ import annotations

from app.domain.events import DomainEvent


class InMemoryEventPublisher:
    """Records published events in memory (also handy as a test spy)."""

    def __init__(self) -> None:
        self.published: list[DomainEvent] = []

    def publish(self, event: DomainEvent) -> None:
        self.published.append(event)
