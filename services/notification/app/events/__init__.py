"""Consuming domain events from the message bus (NTF-201).

The reading half of commerce's :mod:`app.events` package: commerce ``XADD``s a versioned
envelope onto a Redis stream, and this package reads it back with a consumer group,
validates it against a schema registry, and hands it to a handler.

The package is deliberately laid out to mirror the publishing side -- ``envelope``,
``factory``, ``memory``, ``redis_stream`` -- so the two halves of the bus are recognizably
a pair and a change to the wire shape has an obvious counterpart to change with it.
"""
