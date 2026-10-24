"""The domain-event publisher port for the Dietary service (NTF-203).

The application layer depends only on this small surface: hand it a domain event and it
reaches the message bus. Keeping it a port lets Redis be one adapter among others (an
in-process one backs dev/CI and tests), so nothing above this seam imports a driver or
assumes a broker is running.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.events import DomainEvent


@runtime_checkable
class EventPublisher(Protocol):
    """Publish a dietary reminder domain event to the notification service's bus."""

    def publish(self, event: DomainEvent) -> None: ...
