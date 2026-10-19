"""A registered push destination (NTF-302).

A device token is the address FCM or APNs hands the app once it is allowed to receive push
notifications. Registering it is what turns "this user exists" into "this user can be
reached", so two properties matter more than the shape of the record:

* **A token belongs to exactly one account at a time.** A phone can be signed out and signed
  in as somebody else, and the provider keeps issuing the same token to the same install.
  If the old owner's registration survived the switch, the new user's notifications and the
  old user's would both be delivered to that phone -- a privacy failure, not a stale row.
  :meth:`DeviceToken.reassigned_to` is therefore part of the lifecycle, not an afterthought.

* **Refresh is not a new device.** Android and iOS both rotate tokens, and clients re-register
  the current one on every launch. Treating each registration as an insert would grow a new
  row per launch and fan every push out to a dozen copies of the same phone. The token
  (platform, value) is the identity; a repeat registration only moves ``updated_at``.

Timestamps are stored UTC and ``updated_at`` never moves backwards. The latter is a small
defence against a replica whose clock is behind: a refresh stamped earlier than the original
registration would make the record look older than it is, and "most recently active device"
would order it wrongly forever.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from app.domain.enums import DevicePlatform
from app.domain.errors import InvalidDeviceToken

MAX_TOKEN_LENGTH = 4_096
"""Provider tokens are well under this; the cap stops a client turning the store into a blob."""


def _as_utc(value: datetime, *, name: str) -> datetime:
    """Require an aware timestamp and normalize it to UTC."""
    offset = value.tzinfo and value.tzinfo.utcoffset(value)
    if offset is None:
        raise InvalidDeviceToken(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _now(now: datetime | None = None) -> datetime:
    return _as_utc(now or datetime.now(UTC), name="updated_at")


def normalize_token(token: str) -> str:
    """Validate a provider token and strip the surrounding whitespace clients sometimes send.

    Interior whitespace is refused rather than removed: no provider issues a token containing
    it, so a value that does is a copy/paste accident or a test double, and silently repairing
    it would store an address that can never receive anything.
    """
    if not isinstance(token, str):
        raise InvalidDeviceToken(f"device token must be a string, got {type(token).__name__}")
    stripped = token.strip()
    if not stripped:
        raise InvalidDeviceToken("device token must not be blank")
    if len(stripped) > MAX_TOKEN_LENGTH:
        raise InvalidDeviceToken(
            f"device token must be at most {MAX_TOKEN_LENGTH} characters, got {len(stripped)}"
        )
    if any(character.isspace() for character in stripped):
        raise InvalidDeviceToken("device token must not contain whitespace")
    return stripped


@dataclass(frozen=True, slots=True)
class DeviceToken:
    """One push destination registered to one user."""

    id: uuid.UUID
    user_id: uuid.UUID
    platform: DevicePlatform
    token: str
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "platform", DevicePlatform(self.platform))
        except ValueError as exc:
            raise InvalidDeviceToken(f"unknown device platform {self.platform!r}") from exc
        object.__setattr__(self, "token", normalize_token(self.token))
        created_at = _as_utc(self.created_at, name="created_at")
        updated_at = _as_utc(self.updated_at, name="updated_at")
        if updated_at < created_at:
            raise InvalidDeviceToken("updated_at must not precede created_at")
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "updated_at", updated_at)

    @classmethod
    def register(
        cls,
        user_id: uuid.UUID,
        platform: DevicePlatform,
        token: str,
        *,
        now: datetime | None = None,
    ) -> DeviceToken:
        """Build a brand-new registration, or raise if the token cannot be a destination."""
        timestamp = _now(now)
        return cls(
            id=uuid.uuid4(),
            user_id=user_id,
            platform=platform,
            token=token,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def belongs_to(self, user_id: uuid.UUID) -> bool:
        """True when this registration is owned by ``user_id``."""
        return self.user_id == user_id

    def refreshed(self, *, now: datetime | None = None) -> DeviceToken:
        """Return the same registration with ``updated_at`` moved forward.

        A refresh never changes the id, the token, or ``created_at``: the device has not
        become a different device, and a client that revoked by the id it was given must still
        be able to do so after re-registering on its next launch.
        """
        timestamp = _now(now)
        return replace(self, updated_at=max(timestamp, self.updated_at))

    def reassigned_to(self, user_id: uuid.UUID, *, now: datetime | None = None) -> DeviceToken:
        """Return a copy now owned by ``user_id`` -- a device that changed accounts.

        ``created_at`` is kept because it describes this registration record's history, while
        ``updated_at`` records the moment the new account took the device over.
        """
        timestamp = _now(now)
        return replace(
            self,
            user_id=user_id,
            updated_at=max(timestamp, self.updated_at),
        )
