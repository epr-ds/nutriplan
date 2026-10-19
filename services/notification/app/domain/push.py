"""The push-delivery vocabulary: one message, one gateway per provider, one failure type.

A notification is provider-agnostic; FCM and APNs are not. This module is the seam between
them, and it is deliberately small. The application layer builds a :class:`PushMessage` and
hands it to whichever :class:`PushGateway` matches the device's platform; it never learns
whether the address was an Android token or an Apple one, and a test can substitute a fake
gateway without standing up either provider.

**Why the failure type carries semantics rather than just a string.** NTF-303 has to answer
two different questions when a send fails: *should we try again?* and *is this address dead?*
They are not the same question. A timeout is retryable and says nothing about the token; a
`BadDeviceToken` is permanent and means the registration must be pruned. Encoding both on
:class:`PushError` keeps that distinction in one place instead of making the delivery path
pattern-match provider-specific error codes it has no business knowing.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from app.domain.enums import DevicePlatform


@dataclass(frozen=True, slots=True)
class PushMessage:
    """One provider-bound message, addressed to exactly one device token.

    ``data`` is the structured payload a client reads after the user taps through; every value
    is a string because that is the only shape both FCM and APNs accept without translation.
    The alert text lives in ``title``/``body`` rather than in ``data`` so a provider that
    renders the notification itself still has something to show.
    """

    token: str
    title: str
    body: str
    data: Mapping[str, str] = field(default_factory=dict)
    badge: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", MappingProxyType(dict(self.data)))


class PushError(Exception):
    """A provider refused a message, with the two questions the caller has to ask answered.

    ``retryable`` is a statement about *this attempt* -- the provider was unavailable, timed
    out, or throttled -- and says nothing about the address. ``dead_token`` is a statement
    about the *address* -- the provider will never accept it again, so the registration
    should be pruned rather than retried. A dead token is never retryable, even if a provider
    also reports a transient condition, because repeating a send to an address that no longer
    exists cannot start working.
    """

    def __init__(
        self,
        code: str,
        *,
        retryable: bool = False,
        dead_token: bool = False,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.retryable = retryable and not dead_token
        self.dead_token = dead_token
        self.details = MappingProxyType(dict(details or {}))
        super().__init__(f"push error {code}")


@runtime_checkable
class PushGateway(Protocol):
    """One provider's send operation, in the application's own terms."""

    platform: DevicePlatform
    """The device platform this gateway delivers to."""

    def send(self, message: PushMessage) -> str:
        """Deliver ``message`` and return the provider's message id.

        Raises :class:`PushError` when the provider refuses it. The return value is for
        logging and receipt correlation, not for status: reaching here at all means the
        provider accepted the message, which is what ``SENT`` records.
        """
        ...
