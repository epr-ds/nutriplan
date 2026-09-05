"""The deduplication store contract -- run against **both** adapters (AC2).

Same discipline as the notification store suite: every test takes the parametrized
``dedupe_store`` factory, so each one executes against the in-process store and against real
Redis. The claim/confirm/release protocol is exactly the kind of thing a hand-written double
gets subtly wrong -- an unguarded release, a confirm that revives a lapsed claim -- and those
mistakes only ever show up as duplicate or missing notifications in production.

The expiry tests use a one-second window and really sleep. Injecting a clock would be faster
but would only prove the in-memory adapter's arithmetic; Redis expires keys on its own clock,
and whether the two agree is the entire question.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from app.adapters.idempotency import IdempotencyWindow
from app.adapters.in_memory_deduplication_store import InMemoryDeduplicationStore
from app.adapters.redis_deduplication_store import RedisDeduplicationStore
from app.domain.dedupe import DedupeKey
from app.domain.enums import NotificationType
from app.domain.repositories import DeduplicationStore
from tests.conftest import DedupeStoreFactory

FAST = IdempotencyWindow(ttl_seconds=1, provisional_seconds=1)
"""Short enough to observe a lapse without a slow test."""


class _UnusedClient:
    """Stands in where only the adapter's shape is under test, never its commands."""

    def get(self, key: str) -> Any: ...
    def set(self, key: str, value: str, **kwargs: Any) -> Any: ...
    def eval(self, script: str, numkeys: int, *args: Any) -> Any: ...


def _key(event_id: str = "evt-1") -> DedupeKey:
    return DedupeKey.for_event(
        event_id,
        user_id=uuid.uuid4(),
        notification_type=NotificationType.ORDER_CONFIRMED,
    )


# -- claiming --------------------------------------------------------------------


def test_the_first_claim_wins(dedupe_store: DedupeStoreFactory) -> None:
    store = dedupe_store()

    claim = store.claim(_key(), "notification-1")

    assert claim.acquired
    assert claim.holder == "notification-1"


def test_a_second_claim_is_refused_and_names_the_original(
    dedupe_store: DedupeStoreFactory,
) -> None:
    """The refusal has to carry the holder, not just a boolean.

    A consumer that only learns "this was handled" cannot tell the caller *what* the user
    was sent; naming the original notification is what lets the duplicate path resolve it.
    """
    store = dedupe_store()
    key = _key()
    store.claim(key, "notification-1")

    claim = store.claim(key, "notification-2")

    assert not claim.acquired
    assert claim.holder == "notification-1"


def test_re_claiming_with_the_same_holder_reports_ownership(
    dedupe_store: DedupeStoreFactory,
) -> None:
    """A retry by the same delivery is not a conflict; it already owns the key."""
    store = dedupe_store()
    key = _key()
    store.claim(key, "notification-1")

    claim = store.claim(key, "notification-1")

    assert claim.acquired
    assert claim.holder == "notification-1"


def test_distinct_keys_do_not_interfere(dedupe_store: DedupeStoreFactory) -> None:
    store = dedupe_store()

    assert store.claim(_key("evt-1"), "n1").acquired
    assert store.claim(_key("evt-2"), "n2").acquired


def test_an_unclaimed_key_has_no_holder(dedupe_store: DedupeStoreFactory) -> None:
    assert dedupe_store().holder_of(_key()) is None


def test_a_claimed_key_reports_its_holder(dedupe_store: DedupeStoreFactory) -> None:
    store = dedupe_store()
    key = _key()
    store.claim(key, "notification-1")

    assert store.holder_of(key) == "notification-1"


def test_a_plain_string_key_works_too(dedupe_store: DedupeStoreFactory) -> None:
    """The port accepts a raw token so a future caller need not own a DedupeKey."""
    store = dedupe_store()

    assert store.claim("raw-token", "n1").acquired
    assert store.holder_of("raw-token") == "n1"


# -- confirming ------------------------------------------------------------------


def test_confirming_keeps_the_key_held(dedupe_store: DedupeStoreFactory) -> None:
    store = dedupe_store()
    key = _key()
    store.claim(key, "notification-1")

    assert store.confirm(key, "notification-1")
    assert store.holder_of(key) == "notification-1"
    assert not store.claim(key, "notification-2").acquired


def test_confirming_a_key_you_do_not_hold_fails(dedupe_store: DedupeStoreFactory) -> None:
    store = dedupe_store()
    key = _key()
    store.claim(key, "notification-1")

    assert not store.confirm(key, "notification-2")
    assert store.holder_of(key) == "notification-1"


def test_confirming_an_unclaimed_key_fails(dedupe_store: DedupeStoreFactory) -> None:
    """Confirm extends an existing lease; it must never create one.

    A confirm that wrote the key would resurrect a claim whose provisional lease had already
    lapsed and been taken over, quietly overruling the delivery that is now authoritative.
    """
    store = dedupe_store()
    key = _key()

    assert not store.confirm(key, "notification-1")
    assert store.holder_of(key) is None


# -- releasing -------------------------------------------------------------------


def test_releasing_frees_the_key_for_the_next_delivery(
    dedupe_store: DedupeStoreFactory,
) -> None:
    store = dedupe_store()
    key = _key()
    store.claim(key, "notification-1")

    assert store.release(key, "notification-1")
    assert store.holder_of(key) is None
    assert store.claim(key, "notification-2").acquired


def test_releasing_a_key_held_by_someone_else_is_refused(
    dedupe_store: DedupeStoreFactory,
) -> None:
    """The ownership guard is not defensive noise -- it prevents a real duplicate.

    If a provisional lease lapses and a redelivery re-claims the key, an unguarded delete by
    the original worker would free *that* claim and let a third delivery write a second
    notification.
    """
    store = dedupe_store()
    key = _key()
    store.claim(key, "notification-1")

    assert not store.release(key, "notification-2")
    assert store.holder_of(key) == "notification-1"


def test_releasing_an_unclaimed_key_is_a_no_op(dedupe_store: DedupeStoreFactory) -> None:
    assert not dedupe_store().release(_key(), "notification-1")


# -- expiry ----------------------------------------------------------------------


def test_an_unconfirmed_claim_lapses(dedupe_store: DedupeStoreFactory) -> None:
    """The provisional lease is what stops a crash from swallowing a notification.

    A worker killed between claiming and writing never confirms; once the short lease runs
    out the redelivered event has to be able to claim the key and deliver for real.
    """
    store = dedupe_store(window=FAST)
    key = _key()
    store.claim(key, "notification-1")

    time.sleep(1.2)

    assert store.holder_of(key) is None
    assert store.claim(key, "notification-2").acquired


def test_a_confirmed_claim_outlives_the_provisional_lease(
    dedupe_store: DedupeStoreFactory,
) -> None:
    store = dedupe_store(window=IdempotencyWindow(ttl_seconds=60, provisional_seconds=1))
    key = _key()
    store.claim(key, "notification-1")
    store.confirm(key, "notification-1")

    time.sleep(1.2)

    assert store.holder_of(key) == "notification-1"
    assert not store.claim(key, "notification-2").acquired


def test_a_lapsed_window_lets_a_much_later_replay_through(
    dedupe_store: DedupeStoreFactory,
) -> None:
    """Dedupe is a window, not a permanent ledger -- the keys have to age out."""
    store = dedupe_store(window=FAST)
    key = _key()
    store.claim(key, "notification-1")
    store.confirm(key, "notification-1")

    time.sleep(1.2)

    assert store.claim(key, "notification-2").acquired


# -- disabled --------------------------------------------------------------------


def test_a_zero_window_disables_deduplication(dedupe_store: DedupeStoreFactory) -> None:
    """A legitimate setting for an environment deliberately replaying a fixture stream."""
    store = dedupe_store(window=IdempotencyWindow(ttl_seconds=0))
    key = _key()

    assert store.claim(key, "notification-1").acquired
    assert store.claim(key, "notification-2").acquired
    assert store.holder_of(key) is None


# -- the port --------------------------------------------------------------------


def test_both_adapters_satisfy_the_port() -> None:
    assert isinstance(InMemoryDeduplicationStore(), DeduplicationStore)
    assert isinstance(RedisDeduplicationStore(_UnusedClient()), DeduplicationStore)


def test_the_factory_built_store_satisfies_the_port(
    dedupe_store: DedupeStoreFactory,
) -> None:
    assert isinstance(dedupe_store(), DeduplicationStore)


# -- in-memory clock seam --------------------------------------------------------


def test_the_in_memory_store_uses_its_injected_clock() -> None:
    """Kept separate from the parity suite: only this adapter has a clock to inject.

    It buys fast, exact tests of the arithmetic; the parity suite above still proves the two
    adapters agree, using real time so Redis's own expiry is what is being measured.
    """
    now = [1_000.0]
    store = InMemoryDeduplicationStore(window=FAST, clock=lambda: now[0])
    key = _key()
    store.claim(key, "notification-1")

    now[0] += 0.5
    assert store.holder_of(key) == "notification-1"

    now[0] += 1.0
    assert store.holder_of(key) is None


def test_the_in_memory_store_forgets_lapsed_claims() -> None:
    """Reads prune what they walk over, so a long-lived process does not leak keys."""
    now = [1_000.0]
    store = InMemoryDeduplicationStore(window=FAST, clock=lambda: now[0])
    key = _key()
    store.claim(key, "notification-1")

    now[0] += 5.0
    store.holder_of(key)

    assert store._claims == {}
