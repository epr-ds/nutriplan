"""Domain-event publishing for the Commerce service (COM-109).

The order aggregate records events (``OrderCreated``/``OrderStatusChanged``); this package turns
them into a versioned wire envelope and pushes them onto a message bus for downstream systems (the
P5 notification service). It follows the same port/adapter/factory shape as ``app.kv``: a thin
:class:`~app.events.publisher.EventPublisher` port with an in-process adapter for dev/CI and a
Redis-streams adapter for production, selected by configuration.
"""
