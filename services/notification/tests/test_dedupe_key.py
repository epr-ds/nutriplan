"""The dedupe key: deterministic, injective, and total over the triple (AC1).

These are the properties the whole story rests on. If the key is not deterministic across
processes, two workers disagree about what has been handled and the user is spammed. If it
is not injective, two unrelated events collide and one of them is silently swallowed. Both
failures are invisible in a single-process test that only compares a key with itself, so
they are asserted directly here.
"""

from __future__ import annotations

import subprocess
import sys
import uuid
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from app.domain.dedupe import DIGEST_LENGTH, Claim, DedupeKey
from app.domain.enums import NotificationType
from app.domain.errors import InvalidDedupeKey, NotificationError

USER = uuid.UUID("11111111-1111-1111-1111-111111111111")
OTHER_USER = uuid.UUID("22222222-2222-2222-2222-222222222222")
SERVICE_ROOT = Path(__file__).resolve().parents[1]


def _key(
    event_id: str = "evt-1",
    *,
    user_id: uuid.UUID = USER,
    notification_type: NotificationType = NotificationType.ORDER_CONFIRMED,
) -> DedupeKey:
    return DedupeKey.for_event(event_id, user_id=user_id, notification_type=notification_type)


# -- determinism -----------------------------------------------------------------


def test_the_same_triple_always_yields_the_same_key() -> None:
    assert _key() == _key()
    assert str(_key()) == str(_key())


def test_the_key_is_stable_across_processes() -> None:
    """The property that actually matters: a replay is usually handled by another worker.

    Python randomizes ``hash()`` per process via ``PYTHONHASHSEED``, so a key built on it
    would agree with itself here and disagree with every other replica in production -- the
    kind of bug that only shows up as users receiving duplicates. Running the derivation in
    a genuinely separate interpreter is the only way to assert it did not happen.
    """
    script = (
        "from app.domain.dedupe import DedupeKey;"
        "from app.domain.enums import NotificationType;"
        "print(DedupeKey.for_event('evt-1',"
        f" user_id='{USER}',"
        " notification_type=NotificationType.ORDER_CONFIRMED))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
        cwd=SERVICE_ROOT,
    )

    assert result.stdout.strip() == str(_key())


def test_the_key_does_not_depend_on_how_the_user_id_was_spelled() -> None:
    from_uuid = DedupeKey.for_event(
        "evt-1", user_id=USER, notification_type=NotificationType.ORDER_CONFIRMED
    )
    from_string = DedupeKey.for_event(
        "evt-1", user_id=str(USER), notification_type=NotificationType.ORDER_CONFIRMED
    )

    assert from_uuid == from_string


def test_the_type_may_be_given_as_its_string_value() -> None:
    assert _key(notification_type=NotificationType.MEAL_REMINDER) == DedupeKey.for_event(
        "evt-1", user_id=USER, notification_type="meal_reminder"
    )


# -- every component is part of the identity -------------------------------------


def test_a_different_event_yields_a_different_key() -> None:
    assert _key("evt-1") != _key("evt-2")


def test_a_different_user_yields_a_different_key() -> None:
    assert _key(user_id=USER) != _key(user_id=OTHER_USER)


def test_a_different_type_yields_a_different_key() -> None:
    """One event legitimately fans out into several notifications for the same user.

    A delivered order raises both the delivery notice and, later, a prompt to rate it. If
    the type were not part of the key the second would be suppressed as a duplicate of the
    first, so this is a behaviour requirement rather than a hashing detail.
    """
    delivered = _key(notification_type=NotificationType.ORDER_DELIVERED)
    reminder = _key(notification_type=NotificationType.MEAL_REMINDER)

    assert delivered != reminder


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (("a:b", "c"), ("a", "b:c")),
        (("evt", "1u"), ("evt1", "u")),
        (("", "abc"), ("abc", "")),
    ],
)
def test_components_cannot_bleed_into_each_other(
    left: tuple[str, str], right: tuple[str, str]
) -> None:
    """Length-prefixing is what stops two different triples from producing one key.

    Naive concatenation makes ``("a:b", "c")`` and ``("a", "b:c")`` indistinguishable, so
    one event would permanently suppress an unrelated one. Event ids come from upstream
    producers, so we do not get to assume they avoid our separator.
    """
    left_event, left_user = left
    right_event, right_user = right

    assert DedupeKey.for_event(
        left_event or "-",
        user_id=left_user,
        notification_type=NotificationType.MEAL_REMINDER,
    ) != DedupeKey.for_event(
        right_event or "-",
        user_id=right_user,
        notification_type=NotificationType.MEAL_REMINDER,
    )


# -- shape -----------------------------------------------------------------------


def test_the_key_reads_as_type_then_digest() -> None:
    """Ops debug this data with redis-cli; an opaque digest alone tells them nothing."""
    key = _key(notification_type=NotificationType.ORDER_IN_TRANSIT)
    type_part, _, digest = str(key).partition(":")

    assert type_part == "order_in_transit"
    assert len(digest) == DIGEST_LENGTH
    assert digest == key.digest


def test_the_digest_is_hex() -> None:
    int(_key().digest, 16)  # raises if the digest is not hex


def test_the_key_is_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        _key().digest = "tampered"  # type: ignore[misc]


# -- rejection -------------------------------------------------------------------


@pytest.mark.parametrize("event_id", ["", "   ", "\t\n"])
def test_a_blank_event_id_is_rejected(event_id: str) -> None:
    """A blank id would collapse every event of a type for a user onto one key.

    The first notification that user ever received would then suppress all the rest --
    a total, silent outage of notifications for exactly one person, which is far worse than
    a loud failure at the boundary.
    """
    with pytest.raises(InvalidDedupeKey):
        _key(event_id)


def test_rejection_is_catchable_as_both_a_domain_error_and_a_value_error() -> None:
    assert issubclass(InvalidDedupeKey, NotificationError)
    assert issubclass(InvalidDedupeKey, ValueError)


def test_an_unknown_notification_type_is_rejected() -> None:
    with pytest.raises(ValueError, match="not a valid NotificationType"):
        DedupeKey.for_event("evt-1", user_id=USER, notification_type="not-a-type")


def test_an_empty_digest_is_rejected() -> None:
    with pytest.raises(InvalidDedupeKey):
        DedupeKey(notification_type=NotificationType.MEAL_REMINDER, digest="")


# -- the claim result ------------------------------------------------------------


def test_an_acquired_claim_is_truthy_and_names_the_caller() -> None:
    claim = Claim(acquired=True, holder="me")

    assert claim
    assert claim.holder == "me"


def test_a_refused_claim_is_falsey_and_names_the_original_holder() -> None:
    claim = Claim(acquired=False, holder="someone-else")

    assert not claim
    assert claim.holder == "someone-else"
