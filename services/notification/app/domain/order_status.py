"""Commerce's order lifecycle, as the Notification context understands it (NTF-202).

This is a **deliberate copy** of Commerce's ``OrderStatus`` (COM-106), not an import.
Notification and Commerce are separate deployables with separate test containers, so there is
nothing to import from; and even if there were, a bounded context that reached into another's
domain model would be coupled to every change made for reasons that have nothing to do with
notifying anybody. What crosses the boundary is the *event contract* -- the strings on the
wire -- and this module is where those strings become meaning on our side.

Two things are modelled here, and they are not the same thing:

**What the status means to a user.** :func:`notification_type_for` maps a status onto the
:class:`~app.domain.enums.NotificationType` that describes it. ``pending`` maps to ``None``:
an order entering its initial state is not news to the person who just placed it.

**How far along the order is.** :data:`PROGRESS` ranks the statuses so a consumer can tell
forward movement from a stale event. This is the whole answer to "out-of-order events
handled" -- see below.

Notification progress is not Commerce's state machine
-----------------------------------------------------
The rank is an ordering over *how newsworthy-late* a status is, which is why ``cancelled``
sits at the top rather than beside the state it interrupts. An order can be cancelled from
any pre-delivery state, and once it is, nothing earlier should ever be announced: telling
someone "your order is being prepared" after telling them it was cancelled is worse than
saying nothing at all. Ranking ``cancelled`` above every non-terminal status makes that
impossible by construction rather than by a special case.

The consequence at the other end -- a late ``cancelled`` outranking a delivered order, and so
being announced -- is the correct behaviour if it ever happens. COM-106 does not permit
``delivered -> cancelled``, so it should not; but if an order we told a user was delivered is
subsequently cancelled, that is news they need, not noise to suppress.

An unrecognised status is a permanent failure
---------------------------------------------
:func:`notification_type_for` raises :class:`UnknownOrderStatus` rather than shrugging. When
Commerce adds a status, this build genuinely cannot say whether it is newsworthy, and the two
ways of guessing are not symmetric: dropping it silently loses a notification forever, while
parking it keeps the event in the dead-letter queue until the mapping ships, after which
NTF-204 replays it and the user hears about it late instead of never. Late is recoverable;
silence is not.

The error raised here is a *domain* error -- this module knows nothing about buses. The
consumer translates it into :class:`~app.events.errors.UnsupportedEvent`, whose docstring
describes this situation exactly: nothing is wrong with the message, the consumer is simply
behind the producer, and a deploy is what fixes it.

That reasoning is the opposite of NTF-201's "unknown event *type* -> ack, do not park", and
the difference is one of scale. The order stream carries every event Commerce publishes, so
unknown types are ordinary background traffic and a dead-letter queue full of them is a queue
nobody reads. A new *order status* is a rare, deliberate change to a lifecycle we already
model -- exactly the signal a dead-letter queue is for.
"""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType

from app.domain.enums import NotificationType
from app.domain.errors import NotificationError


class UnknownOrderStatus(NotificationError):
    """A status string this build has no mapping for -- see the module docstring."""


class OrderStatus(StrEnum):
    """The lifecycle states Commerce publishes on the order stream (COM-106)."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    PREPARING = "preparing"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

    @classmethod
    def parse(cls, value: object) -> OrderStatus:
        """Coerce a wire value, raising :class:`UnknownOrderStatus` rather than ``ValueError``.

        The distinction matters downstream: ``ValueError`` is an anonymous programming error
        that NTF-201 would retry five times before parking, whereas this is a permanent,
        self-describing condition that should be parked on the first delivery.
        """
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise UnknownOrderStatus(f"order status must be a string, got {type(value).__name__}")
        try:
            return cls(value.strip())
        except ValueError:
            raise UnknownOrderStatus(f"unknown order status {value!r}") from None

    @property
    def is_terminal(self) -> bool:
        """True once the order will not move again."""
        return self in _TERMINAL


_TERMINAL = frozenset({OrderStatus.DELIVERED, OrderStatus.CANCELLED})

PROGRESS: MappingProxyType[OrderStatus, int] = MappingProxyType(
    {
        OrderStatus.PENDING: 0,
        OrderStatus.CONFIRMED: 1,
        OrderStatus.PREPARING: 2,
        OrderStatus.IN_TRANSIT: 3,
        OrderStatus.DELIVERED: 4,
        # Above delivered on purpose -- a cancellation must never be overtaken by a stale
        # earlier status. See the module docstring.
        OrderStatus.CANCELLED: 5,
    }
)
"""How far along an order is, for deciding whether an event is forward movement or stale."""

NO_PROGRESS = -1
"""The rank of an order nothing has been recorded for, below even ``pending``."""


_NOTIFICATION_TYPES: MappingProxyType[OrderStatus, NotificationType] = MappingProxyType(
    {
        OrderStatus.CONFIRMED: NotificationType.ORDER_CONFIRMED,
        OrderStatus.PREPARING: NotificationType.ORDER_PREPARING,
        OrderStatus.IN_TRANSIT: NotificationType.ORDER_IN_TRANSIT,
        OrderStatus.DELIVERED: NotificationType.ORDER_DELIVERED,
        OrderStatus.CANCELLED: NotificationType.ORDER_CANCELLED,
    }
)


def progress_of(status: OrderStatus | str) -> int:
    """Return how far along ``status`` is; higher means later in the order's life."""
    return PROGRESS[OrderStatus.parse(status)]


def notification_type_for(status: OrderStatus | str) -> NotificationType | None:
    """Return the notification a status warrants, or ``None`` when it warrants none.

    ``None`` is reserved for statuses we understand and have decided are not news
    (``pending``). A status we do *not* understand raises instead, because those are not the
    same answer and treating them alike is how a new order status becomes a silent outage.
    """
    return _NOTIFICATION_TYPES.get(OrderStatus.parse(status))
