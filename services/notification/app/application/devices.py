"""Register, refresh, list, and revoke push destinations (NTF-302).

Three lifecycle events reach this layer, and each has a different answer:

* **Register** -- the app launches and hands over its current token. If the token is already
  known to this user it is a *refresh*: the record keeps its id and ``created_at`` and moves
  ``updated_at``. If it is unknown, a new record is created. Re-registering on every launch is
  the normal path, not an error.
* **Reassign** -- the same token arrives under a different account, which happens whenever a
  phone signs out and signs in as somebody else. The record moves to the new owner; it must
  not be duplicated, because the provider will deliver to that phone exactly once per token
  and the previous owner must stop receiving on it.
* **Prune** -- a provider reports the token as dead (uninstalled app, revoked permission).
  The registration is removed by token, without needing to know whose it was: at that moment
  the only useful action is to forget the address.

Revocation by id is owner-scoped, like every other read and write in this service. Pruning is
the exception by design -- it is driven by provider feedback, not by a user request, and
requiring an owner lookup first would leave a dead token in place whenever that lookup was the
thing that failed.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from app.domain.device_token import DeviceToken
from app.domain.enums import DevicePlatform
from app.domain.errors import DeviceTokenNotFound
from app.domain.repositories import DeviceTokenRepository


class DeviceRegistrationService:
    """The push-destination use cases, over one persistence port."""

    def __init__(self, repository: DeviceTokenRepository) -> None:
        self._repository = repository

    def register(
        self,
        user_id: uuid.UUID,
        platform: DevicePlatform,
        token: str,
        *,
        now: datetime | None = None,
    ) -> DeviceToken:
        """Register ``token`` for ``user_id``, refreshing or reassigning an existing record.

        The token -- not the id the service mints -- decides whether this is new, so a client
        that re-registers on every launch does not accumulate rows. Whichever branch is taken,
        the repository's ``upsert`` writes last, so two concurrent registrations of one token
        converge on a single record rather than leaving a duplicate behind.
        """
        candidate = DeviceToken.register(user_id, platform, token, now=now)
        existing = self._repository.find_by_token(candidate.platform, candidate.token)
        if existing is None:
            return self._repository.upsert(candidate)
        if existing.belongs_to(user_id):
            return self._repository.upsert(existing.refreshed(now=now))
        return self._repository.upsert(existing.reassigned_to(user_id, now=now))

    def list_devices(self, user_id: uuid.UUID) -> tuple[DeviceToken, ...]:
        """Every device registered to the caller, most recently registered first."""
        return tuple(self._repository.list_for_user(user_id))

    def revoke(self, user_id: uuid.UUID, device_id: uuid.UUID) -> None:
        """Remove one of the caller's devices, or raise :class:`DeviceTokenNotFound`.

        An id that never existed, one already revoked, and one belonging to somebody else all
        raise the same error, so the endpoint cannot be used to discover another user's
        registrations by enumerating UUIDs.
        """
        if not self._repository.delete(device_id, user_id=user_id):
            raise DeviceTokenNotFound(f"device {device_id} is not available")

    def prune(self, platform: DevicePlatform, token: str) -> bool:
        """Forget a token the provider reports as dead; ``True`` if a record was removed.

        Called from the delivery path when FCM/APNs answers "unregistered" or "bad token".
        The return value is for logging, not control flow: a token that was already gone is
        still a success, since the desired end state -- not registered -- holds either way.
        """
        return self._repository.delete_by_token(platform, token)
