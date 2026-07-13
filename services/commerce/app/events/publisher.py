"""The domain-event publisher port (COM-109).

The application layer depends only on this small surface: hand it a domain event and it reaches the
message bus. Keeping it a port lets Redis be one adapter among others (an in-process one backs
dev/CI and tests), so nothing above this seam imports a driver or assumes a broker is running.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.events import DomainEvent


@runtime_checkable
class EventPublisher(Protocol):
    """Publishes a single order domain event to the message bus.

    Implementations serialize the event to the versioned envelope (see
    :mod:`app.events.envelope`) and hand it to a broker. Publishing is fire-and-forget from a use
    case's perspective -- see :mod:`app.events.resilient` for how a transport failure is prevented
    from failing the originating write.
    """

    def publish(self, event: DomainEvent) -> None: ...
