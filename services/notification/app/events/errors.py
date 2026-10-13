"""Failures raised while consuming an event, split by whether retrying could ever help.

This split is the single most consequential distinction in the package, because it decides
whether a delivery is acknowledged. A message bus offers redelivery as its only remedy, and
redelivery is worth nothing against a fault that is a property of the *message* rather than
of the moment: a truncated payload will still be truncated in ten seconds, and a schema
version this build has never heard of will still be unknown after a thousand retries.

So the errors below are **permanent**. Raising one takes the event out of the retry path and
parks it (NTF-204), and the delivery is acknowledged -- not because it succeeded, but because
leaving it pending would have the reclaim pass re-serve it on every cycle forever, burning
the consumer on an event it has already proven it cannot read.

Transient failures are deliberately *not* modelled here. A store outage, a DNS blip, a
timeout -- those arrive as whatever exception the failing library raises, and the dispatcher
treats any exception it does not recognise as retryable. That default is the safe one: a new
failure mode nobody has classified yet gets redelivered rather than silently discarded.
"""

from __future__ import annotations


class EventError(Exception):
    """Base class for permanent, non-retryable failures to consume an event."""


class MalformedEvent(EventError, ValueError):
    """The payload is not a well-formed envelope and never will be.

    Covers a non-JSON body, a JSON value that is not an object, a missing or empty required
    envelope field, and a timestamp that cannot be read as an instant. Every one of them is a
    defect in what was published; no amount of redelivery repairs the bytes already on the
    stream.
    """


class UnsupportedEvent(EventError):
    """A recognised event type arrived at a schema version this build cannot interpret.

    Distinct from :class:`MalformedEvent` because nothing is wrong with the message -- the
    consumer is simply behind the producer. That makes it the one permanent failure that a
    *deploy* fixes, which is exactly why the event is parked rather than dropped: NTF-204's
    replay hands it to the newer build that does understand it.
    """
