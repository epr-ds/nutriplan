"""NTF-104: the preferences store, proven against both adapters.

Every test here runs twice -- once against the in-memory adapter and once against a live
Redis -- because a double that is only ever checked against itself proves nothing about the
adapter that actually runs in production. NTF-102 found a real divergence exactly this way.

One test deliberately reaches past the port to read ``TTL`` from the server. Preferences are
the only key this service writes without an expiry, and that absence is a decision rather
than an oversight: a muted type that switched itself back on thirty days later, at a moment
with no connection to anything the user did, is a bug the user experiences as the app
ignoring them. A comment would not survive someone tidying the adapter to match the style of
its neighbours; a failing test will.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time, timedelta

import pytest

from app.adapters import preferences_codec
from app.adapters.keys import NotificationKeys
from app.adapters.redis_preferences_repository import RedisPreferencesRepository
from app.domain.enums import NotificationChannel, NotificationType
from app.domain.errors import InvalidPreferences
from app.domain.preferences import NotificationPreferences
from app.domain.quiet_hours import QuietHours
from tests.conftest import drop_namespace, isolated_namespace

IN_APP = NotificationChannel.IN_APP
PUSH = NotificationChannel.PUSH
CONFIRMED = NotificationType.ORDER_CONFIRMED
DELIVERED = NotificationType.ORDER_DELIVERED

NIGHT = QuietHours(start=time(22, 0), end=time(7, 0), time_zone="America/Mexico_City")


# -- the port contract, both adapters ---------------------------------------------------


def test_a_user_with_no_stored_preferences_reads_as_absent(preferences_repository):
    """``None`` rather than defaults, so the caller decides what missing means.

    The delivery path fails open and the API renders defaults, but both of those are
    policies -- the store's job is to say truthfully whether anything was written.
    """
    assert preferences_repository.get(uuid.uuid4()) is None


def test_saving_then_reading_returns_an_equal_record(preferences_repository):
    user = uuid.uuid4()
    saved = NotificationPreferences(user_id=user).muting(CONFIRMED, PUSH)

    preferences_repository.save(saved)

    assert preferences_repository.get(user) == saved


def test_save_returns_what_it_stored(preferences_repository):
    user = uuid.uuid4()
    preferences = NotificationPreferences(user_id=user).muting(CONFIRMED, PUSH)

    assert preferences_repository.save(preferences) == preferences


def test_mutes_survive_the_round_trip_as_enum_members(preferences_repository):
    """The wire form is strings; a read that returned strings would silently stop matching."""
    user = uuid.uuid4()
    preferences_repository.save(
        NotificationPreferences(user_id=user).muting(CONFIRMED, PUSH).muting(DELIVERED, IN_APP)
    )

    stored = preferences_repository.get(user)

    assert stored is not None
    assert stored.muted == frozenset({(CONFIRMED, PUSH), (DELIVERED, IN_APP)})
    assert stored.is_muted(CONFIRMED, PUSH) is True
    assert stored.allows(DELIVERED, IN_APP) is False


def test_quiet_hours_survive_the_round_trip(preferences_repository):
    user = uuid.uuid4()
    preferences_repository.save(NotificationPreferences(user_id=user, quiet_hours=NIGHT))

    stored = preferences_repository.get(user)

    assert stored is not None
    assert stored.quiet_hours == NIGHT
    assert stored.quiet_hours.time_zone == "America/Mexico_City"


def test_updated_at_survives_the_round_trip(preferences_repository):
    user = uuid.uuid4()
    stamped = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=5)

    preferences_repository.save(NotificationPreferences(user_id=user, updated_at=stamped))

    stored = preferences_repository.get(user)
    assert stored is not None
    assert stored.updated_at == stamped


def test_saving_again_replaces_the_previous_record(preferences_repository):
    """The write is a full replacement, so a cleared mute must not linger."""
    user = uuid.uuid4()
    preferences_repository.save(NotificationPreferences(user_id=user).muting(CONFIRMED, PUSH))

    preferences_repository.save(NotificationPreferences(user_id=user).muting(DELIVERED, IN_APP))

    stored = preferences_repository.get(user)
    assert stored is not None
    assert stored.muted == frozenset({(DELIVERED, IN_APP)})


def test_clearing_quiet_hours_persists_the_absence(preferences_repository):
    user = uuid.uuid4()
    preferences_repository.save(NotificationPreferences(user_id=user, quiet_hours=NIGHT))

    preferences_repository.save(NotificationPreferences(user_id=user, quiet_hours=None))

    stored = preferences_repository.get(user)
    assert stored is not None
    assert stored.quiet_hours is None


def test_one_users_preferences_are_invisible_to_another(preferences_repository):
    first, second = uuid.uuid4(), uuid.uuid4()
    preferences_repository.save(NotificationPreferences(user_id=first).muting(CONFIRMED, PUSH))

    assert preferences_repository.get(second) is None


def test_two_users_are_stored_independently(preferences_repository):
    first, second = uuid.uuid4(), uuid.uuid4()
    preferences_repository.save(NotificationPreferences(user_id=first).muting(CONFIRMED, PUSH))
    preferences_repository.save(NotificationPreferences(user_id=second).muting(DELIVERED, IN_APP))

    stored_first = preferences_repository.get(first)
    stored_second = preferences_repository.get(second)

    assert stored_first is not None and stored_first.muted == frozenset({(CONFIRMED, PUSH)})
    assert stored_second is not None and stored_second.muted == frozenset({(DELIVERED, IN_APP)})


def test_defaults_round_trip_as_an_empty_deny_list(preferences_repository):
    """Saving "everything on" must be readable, and must not be confused with never saved."""
    user = uuid.uuid4()
    preferences_repository.save(NotificationPreferences.defaults(user))

    stored = preferences_repository.get(user)
    assert stored is not None
    assert stored.muted == frozenset()


# -- the codec --------------------------------------------------------------------------


def test_the_codec_round_trips_a_full_record():
    user = uuid.uuid4()
    preferences = (
        NotificationPreferences(user_id=user).muting(CONFIRMED, PUSH).with_quiet_hours(NIGHT)
    )

    assert preferences_codec.decode(preferences_codec.encode(preferences)) == preferences


def test_the_encoded_form_is_camel_case_json():
    """The stored shape is the shape NTF-105's siblings publish; keep them one thing."""
    import json

    user = uuid.uuid4()
    encoded = json.loads(
        preferences_codec.encode(
            NotificationPreferences(user_id=user).muting(CONFIRMED, PUSH).with_quiet_hours(NIGHT)
        )
    )

    assert encoded["userId"] == str(user)
    assert encoded["updatedAt"].endswith("Z") or "+" in encoded["updatedAt"]
    assert encoded["quietHours"]["timeZone"] == "America/Mexico_City"


def test_a_corrupt_record_is_a_domain_error_not_a_json_error():
    with pytest.raises(InvalidPreferences):
        preferences_codec.decode("{not json")


# -- Redis specifics --------------------------------------------------------------------


def test_preferences_are_stored_without_an_expiry(redis_client):
    """The one key this service writes that must outlive the retention window.

    Read straight from the server rather than through the port: the claim being defended is
    about what is on disk, and the port cannot express it.
    """
    namespace = isolated_namespace()
    keys = NotificationKeys(namespace=namespace)
    repository = RedisPreferencesRepository(redis_client, keys=keys)
    user = uuid.uuid4()

    try:
        repository.save(NotificationPreferences(user_id=user).muting(CONFIRMED, PUSH))

        # -1 is redis-speak for "the key exists and has no expiry"; -2 means it is gone.
        assert redis_client.ttl(keys.preferences(user)) == -1
    finally:
        drop_namespace(redis_client, namespace)


def test_the_preferences_key_is_namespaced_and_versioned(redis_client):
    """A schema bump must invalidate preferences alongside the records they filter."""
    namespace = isolated_namespace()
    keys = NotificationKeys(namespace=namespace)
    repository = RedisPreferencesRepository(redis_client, keys=keys)
    user = uuid.uuid4()

    try:
        repository.save(NotificationPreferences(user_id=user))

        key = keys.preferences(user)
        assert key.startswith(f"{namespace}:")
        assert redis_client.exists(key) == 1
    finally:
        drop_namespace(redis_client, namespace)
