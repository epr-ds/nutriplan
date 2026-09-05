"""The Redis key scheme: namespaced, versioned, and one key shape per concern."""

from __future__ import annotations

import uuid

from app.adapters.keys import SCHEMA_VERSION, NotificationKeys

USER = uuid.UUID("11111111-1111-4111-8111-111111111111")
NOTIFICATION = uuid.UUID("22222222-2222-4222-8222-222222222222")


def test_the_default_namespace_matches_the_service() -> None:
    assert NotificationKeys().prefix == f"notification:{SCHEMA_VERSION}"


def test_every_key_is_namespaced_and_versioned() -> None:
    keys = NotificationKeys(namespace="staging")

    built = [keys.record(NOTIFICATION), keys.feed(USER), keys.unread(USER)]

    assert all(key.startswith(f"staging:{SCHEMA_VERSION}:") for key in built)


def test_namespaces_keep_environments_apart() -> None:
    # Two environments can share one Redis without reading each other's notifications.
    assert NotificationKeys(namespace="a").record(NOTIFICATION) != NotificationKeys(
        namespace="b"
    ).record(NOTIFICATION)


def test_the_three_key_shapes_are_distinct() -> None:
    keys = NotificationKeys()

    built = {keys.record(NOTIFICATION), keys.feed(USER), keys.unread(USER)}

    assert len(built) == 3


def test_a_user_s_indexes_are_scoped_to_that_user() -> None:
    keys = NotificationKeys()
    other = uuid.UUID("33333333-3333-4333-8333-333333333333")

    assert keys.feed(USER) != keys.feed(other)
    assert str(USER) in keys.feed(USER)


def test_ids_may_be_passed_as_uuids_or_strings() -> None:
    keys = NotificationKeys()

    assert keys.record(NOTIFICATION) == keys.record(str(NOTIFICATION))


def test_index_for_selects_the_unread_subset_or_the_whole_feed() -> None:
    keys = NotificationKeys()

    assert keys.index_for(USER, unread_only=True) == keys.unread(USER)
    assert keys.index_for(USER, unread_only=False) == keys.feed(USER)


def test_the_keys_object_is_frozen() -> None:
    keys = NotificationKeys()

    try:
        keys.namespace = "other"  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("NotificationKeys must be immutable")
