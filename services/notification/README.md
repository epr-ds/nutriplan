# Notification Service

**Bounded context:** Notification. Push notifications (FCM/APNs), order-status events, and
plan reminders, driven by domain events over the message bus.

- **Framework:** Python 3.12 · FastAPI (per ADR 0004)
- **Datastore:** Redis
- **Port:** 8084
- **Consumes:** order lifecycle events from Commerce; plan events from Dietary.

## Status

Phase 5 in progress. **NTF-101** delivered the scaffold: the `NOTIFICATION_`-prefixed
configuration surface for all three dependencies (Redis, the message bus, the push
providers), an environment-aware readiness evaluation, and `/health` + `/health/ready`.
**NTF-102** added the notification model and its Redis-backed store, so notifications now
persist and can be listed per user. **NTF-103** made writing one idempotent, so a redelivered
event cannot notify a user twice. **NTF-105** put the first read API in front of that store --
the in-app feed -- and with it this service's first published contract,
[`contracts/notification.openapi.yaml`](../../contracts/notification.openapi.yaml).
**NTF-104** added per-type, per-channel preferences and a nightly quiet-hours window, and
wired them into the write path, so a user can now turn a notification off and have it stay
off. **NTF-201** built the consumer framework and the versioned event-schema registry, so the
service can read Commerce's order stream, validate what it finds, and settle every delivery
exactly once. **NTF-202** plugged the first real handler into that framework: an order event
now becomes a notification in the user's feed. Delivery is still in-app only -- push arrives
in NTF-301.

## Layout

```
app/
  domain/enums.py       # notification type, channel, delivery status
  domain/notification.py# the immutable Notification record
  domain/dedupe.py      # the deterministic (event, user, type) key
  domain/quiet_hours.py # the nightly window, in the user's own zone
  domain/preferences.py # the per-type, per-channel deny-list
  domain/order_status.py# the order vocabulary and how far an order has progressed
  domain/repositories.py# the persistence and deduplication ports
  application/notification_recorder.py  # the idempotent, preference-gated write path
  application/feed.py     # the paged feed query, badge count, and mark-read use cases
  application/preferences.py  # the settings-screen matrix and the replace use case
  application/order_status_consumer.py  # order event -> notification
  events/envelope.py    # the wire envelope Commerce publishes, parsed
  events/registry.py    # the versioned schema registry and its four verdicts
  events/consumer.py    # the EventConsumer port and DeliveredEvent
  events/dispatcher.py  # settle-or-retry: the outcome table
  events/dead_letter.py # where a permanently-failed event is parked
  events/redis_stream.py# Redis Streams consumer group adapter
  events/memory.py      # in-process adapter, PEL semantics and all
  events/worker.py      # the poll/reclaim loop and its stop signal
  events/factory.py     # picks the consumer from configuration
  adapters/codec.py     # JSON record <-> Notification
  adapters/preferences_codec.py  # JSON record <-> NotificationPreferences
  adapters/keys.py      # the Redis key scheme
  adapters/retention.py # the age + length window both stores enforce
  adapters/idempotency.py  # the replay window + provisional claim length
  adapters/redis_notification_repository.py
  adapters/in_memory_notification_repository.py
  adapters/redis_deduplication_store.py
  adapters/in_memory_deduplication_store.py
  adapters/redis_preferences_repository.py
  adapters/in_memory_preferences_repository.py
  adapters/redis_order_progress.py       # the monotonic progress mark, in Redis
  adapters/in_memory_order_progress.py   # the same mark, in process
  adapters/factory.py   # picks the stores from configuration
  core/config.py        # NOTIFICATION_-prefixed settings (Redis, bus, push providers)
  core/readiness.py     # pure, environment-aware readiness evaluation
  core/probes.py        # the only place that opens a real connection
  core/principal.py     # the authenticated caller
  core/security.py      # RS256 bearer verification against the identity JWKS
  api/deps.py           # the composition root (FastAPI Depends)
  api/errors.py         # RFC 7807 application/problem+json
  api/schemas.py        # the camelCase wire shapes
  api/notifications.py  # GET /notifications, /unread-count, POST /{id}/read
  api/preferences.py    # GET + PUT /notifications/preferences
  api/health.py         # GET /health, GET /health/ready
  main.py               # FastAPI wiring
tests/                  # pytest
```

## The notification store

A notification is immutable: reading it or recording a delivery receipt returns a new
record, so a whole-record write is always what reaches the store. Delivery status
(`pending → sent → delivered`, or `failed` / `suppressed`) and read-state (`readAt`) move
independently -- a push suppressed by quiet hours is still recorded in-app, and can still
be read there.

Three keys back it, all namespaced and versioned:

```
{ns}:v1:n:{id}              the JSON record        (string, EX remaining-window)
{ns}:v1:u:{user}:feed       every id, newest first (sorted set)
{ns}:v1:u:{user}:unread     the unread subset      (sorted set)
```

The two per-user sorted sets are the feed index: a page is a `ZREVRANGE` slice plus an
`MGET`, and the unread badge is a `ZCOUNT`. Unread is a sorted set rather than a plain set
so it can be trimmed by the same age horizon as the feed -- a `SCARD` would drift upward
forever as old unread records expired underneath it.

**Retention** is a rolling window bounded two ways: by age
(`NOTIFICATION_FEED_TTL_SECONDS`, 30 days) and by count
(`NOTIFICATION_FEED_MAX_ENTRIES`, 500 per user), because a busy account could otherwise
grow an unbounded index well inside the window. A record's lease runs from its **creation
time**, not from when it was written, so replaying an old event -- which the NTF-201
consumer must tolerate -- cannot resurrect a months-old notification at the top of the
feed. Adding a notification from outside the window is a no-op.

Because a sorted-set member cannot carry its own TTL, an index entry can outlive the record
it points at. Reads skip such ids and remove the stale pointers they walked over, which is
why a page may come back shorter than the requested limit.

Set `NOTIFICATION_REDIS_URL` and the store is Redis-backed and shared across replicas;
leave it blank and an in-process store stands in, which is correct for dev, CI, and a single
container -- and is exactly the condition `/health/ready` warns about outside production and
fails on inside it.

## Idempotent delivery

A message bus redelivers. Redis Streams re-serve a pending entry whenever a consumer dies
mid-batch, a deploy restarts a pod, or NTF-204 replays a dead-letter, so "one event, one
notification" is not something the bus can promise. `NotificationRecorder` is the write path
consumers use, and it establishes that property here:

```python
result = recorder.record(notification, event_id=message_id)
if result.duplicate:
    ...  # already handled; result.notification is the original
```

Identity is the triple **(event, user, type)** -- not the event alone, because one order
event legitimately raises a delivery notice *and* a prompt to rate the order, and reaches
every user party to the order. The key is a SHA-256 digest over the length-prefixed triple.
Length-prefixing makes it injective: plain concatenation would let `("order:1", "u")` and
`("order", "1:u")` collide, so one event would permanently suppress an unrelated one. And
the digest is SHA-256 rather than Python's `hash()`, which is randomized per process by
`PYTHONHASHSEED` -- a key built on it would agree with itself in one worker and disagree with
every other replica, which is exactly the bug you cannot reproduce locally.

Claiming is **two-phase**, and the reason is the difference between the two ways this can go
wrong:

1. `claim` takes the key under a short provisional lease (`NOTIFICATION_DEDUPE_CLAIM_SECONDS`),
2. the notification is written,
3. `confirm` extends the lease to the full replay window (`NOTIFICATION_DEDUPE_TTL_SECONDS`).

Claiming *before* the write is what prevents the duplicate. The short first lease is what
stops that choice from converting a crash into a permanently swallowed notification: a worker
killed between steps 1 and 2 never confirms, the lease lapses on its own, and the redelivered
event gets through. A write that *raises* -- the common case, a store outage -- releases the
claim immediately, so the retry does not even wait for the lease. Releasing is a
compare-and-delete (a Lua script, the same ownership guard Redlock uses), because under a
lapsed lease another delivery may already hold the key and an unguarded `DEL` would free
*its* claim and let a third delivery through.

The replay window is deliberately much shorter than the feed's retention. If it were longer,
a replay could be suppressed on behalf of an original that had already aged out, and the user
would see neither. Setting `NOTIFICATION_DEDUPE_TTL_SECONDS=0` turns deduplication off, which
is only sensible when deliberately replaying a fixture stream.

## The in-app feed API

Three endpoints, all authenticated with an RS256 bearer token verified against the identity
service's JWKS. **The feed is always the caller's own**: the user id comes from the token's
`sub`, never from a query parameter, so there is no request a client can make that reads
somebody else's notifications.

| endpoint | purpose |
| --- | --- |
| `GET /notifications` | the caller's feed, newest first, paged; `unreadOnly=true` filters |
| `GET /notifications/unread-count` | just the badge, when a client doesn't need the page |
| `POST /notifications/{id}/read` | mark one read; returns the updated notification |

Paging is `page` (1-based) and `limit` (1-100, default 20). The response carries `hasMore`,
which is answered by **over-fetching one record** rather than counting the feed. That is
honest only because expiry is monotonic in feed order: every record's lease runs from its
`created_at` against one uniform TTL, and the feed is newest-first, so live records are
always a *prefix* of the index and a short page really is the tail. **If a later story gives
records individual lifetimes, that argument collapses and `hasMore` has to become a real
count** -- the reasoning is written out in `app/application/feed.py`.

`unreadCount` is the badge for the whole feed, so it is deliberately *not* a total of
`items` and does not change when `unreadOnly` is set. It is also a separate read from the
page, so a mark-read landing between the two can make them disagree by one; that is a
snapshot, not an invariant, and the next poll corrects it. Making them atomic would mean
locking a user's feed reads on shared Redis to fix a discrepancy nobody can perceive.

Marking an unknown id, an expired one, or another user's notification all return the **same**
404 with the same message, so the endpoint cannot be used to discover which notification ids
exist. Every 4xx/5xx is `application/problem+json` (RFC 7807), matching the other services.

The wire shape is the stored shape minus the owner plus `isRead` -- `NotificationResponse`
projects through the same `codec.to_record` the store writes with, so a renamed key breaks
the projection loudly instead of letting the API and the store drift apart quietly.

## Notification preferences and quiet hours

Two endpoints, owner-scoped by the token subject exactly as the feed is:

| endpoint | purpose |
| --- | --- |
| `GET /notifications/preferences` | the caller's complete matrix, every type listed |
| `PUT /notifications/preferences` | replace it wholesale; returns what is now stored |

A user who has never saved anything gets the **defaults** -- everything enabled, no quiet
hours -- rather than a `404`. They do have preferences; they simply have not changed any.

### Stored as a deny-list, never as a matrix

Only the *mutes* are persisted. It would be simpler to store the matrix the settings screen
shows, and it would be wrong: `NotificationType` grows, and a matrix written by last
release's client says nothing about a type added since. Reading "absent" as "disabled" would
then silently mute a brand-new notification for every existing user, on their behalf, without
anyone choosing it. **Absent means enabled.** The full matrix is materialised on read by
iterating the enum, so a new type appears on every settings screen the day it ships.

`PUT` is a replacement, not a patch: a type omitted from `types` returns to enabled, and
`quietHours: null` clears the window. That is also why `types` is **required** with no
default -- a client that forgot the field would otherwise be sending "switch everything back
on". Listing the same type twice is a `422` rather than last-wins, since two rows for one
type are two different answers to the same question and neither is more likely to be meant.

### Quiet hours suppress push only

The in-app feed is pull-based and silent. Withholding an entry from it overnight would spare
the user nothing and would either surface the notification out of order in the morning or
lose it outright. So a notification recorded inside the window still lands in the feed; only
the push channel is dropped, and if push was the *only* channel it was going to, the delivery
is suppressed entirely.

The window is stored as **local wall-clock times plus an IANA zone name**, never as an
offset. Daylight saving is a non-issue here only because of the direction of conversion:
turning an instant into a local time (`astimezone`) is total and unambiguous, while the
reverse is not -- 02:30 does not exist on a spring-forward night and happens twice on a
fall-back night. Storing an offset would quietly shift "ten at night" by an hour twice a
year. The window is half-open, `[start, end)`, and **wrapping past midnight is the normal
case** (`22:00`-`07:00` is one window, not two); `start == end` is rejected, since it reads
equally well as "no window" and "all day".

### The gate runs before the dedupe claim

`NotificationRecorder` checks preferences *before* claiming the dedupe key, and the ordering
is load-bearing. A suppressed notification that burned its key would leave NTF-204's
dead-letter replay -- run after the user turns the type back on -- refused as a duplicate of
a notification that never existed. A suppressed delivery therefore leaves the key free.

If the preferences store is unavailable the recorder **fails open**: it logs
`notification.preferences.unavailable` at WARNING and delivers unfiltered. The alternative is
withholding notifications a user asked for because a side lookup failed, which is worse than
sending one they had muted.

Preferences never expire. They are the user's own configuration, not a cached derivative, so
the Redis write carries no `EX` -- asserted by reading `TTL == -1` back from a live server.

## Consuming events

Commerce publishes order lifecycle events to a Redis stream (`COM-109`); this service reads
them from the stream named by `NOTIFICATION_ORDER_EVENT_STREAM`, which defaults to
`commerce.order-events` and must match the publisher exactly. The worker runs as its **own
process**, not as a FastAPI lifespan task -- a consumer restarted by an HTTP autoscaler is a
consumer whose backlog grows with traffic, and it must be possible to drain a backlog without
serving a single request:

```bash
python -m app.events.worker
```

### The consumer group starts at the end of the stream

`ensure_group` creates the group at `$`, never `0`. Starting at `0` would, on the very first
deploy, replay the entire history of the order stream and notify every user about every order
they have ever placed. NTF-103's dedupe cannot save us there -- no keys exist for events that
were never handled -- so the offset is the only thing standing between a green deploy and a
mass mis-notification. The cost is that events published before the group exists are never
seen, which is the correct trade for a notification service.

### Two identifiers, and which one dedupe uses

Each delivery carries a `delivery_id` (the broker's entry id, assigned on `XADD`) and an
`event_id` (the producer's id, inside the payload). They are not interchangeable: NTF-204's
replay re-adds a parked event, which mints a **new** entry id while keeping the original
envelope id. Deduplication therefore keys on `event_id` -- keying on the entry id would let a
replay through as if it were a new event.

### Settle or retry

Every delivery ends in exactly one of these, and `EventDispatcher` is the only place that
decides which:

| outcome | when | what happens |
| --- | --- | --- |
| handled | a registered handler returned | ack |
| skipped | no handler registered for the type | ack |
| skipped | the registry does not know the type | ack, **not** parked |
| parked | the schema version is unsupported | dead-letter, then ack |
| parked | required data is missing, or a handler raised `EventError` | dead-letter, then ack |
| parked | the retry budget is exhausted | dead-letter, then ack |
| retried | any other exception | no ack; redelivered after the idle window |

Two of those rows carry the load. **A permanent failure is acked after parking** -- leaving it
pending only means the reclaim pass serves it again and parks it again, forever. And **an
unrecognised exception is treated as transient**: guessing "permanent" loses a notification
silently, whereas guessing "transient" costs a few retries and then hits the budget, which
parks it anyway. The budget is the backstop that makes optimism safe.

An **unknown type is acked, not parked**, because producers add event types routinely and a
dead-letter queue full of ordinary traffic is a dead-letter queue nobody reads. An
**unsupported version is parked**, because a version bump is precisely the signal that the
meaning of an event we *do* handle has changed.

### Reclaiming stalled work

A consumer that dies mid-batch leaves its messages pending. The worker periodically reclaims
entries idle longer than `NOTIFICATION_EVENT_RECLAIM_IDLE_MS`, using `XPENDING` + `XCLAIM`
rather than `XAUTOCLAIM`: the delivery count is the entire reason for reclaiming (it drives
the retry budget) and `XAUTOCLAIM` does not report it. `XCLAIM` itself increments that
counter, so the reported attempt is `times_delivered + 1`. The idle window is configured to
comfortably exceed the block time, because reclaiming a message that is merely slow
manufactures a duplicate delivery.

### The in-memory consumer reproduces the same semantics

`InMemoryEventConsumer` keeps a real pending-entries list, tracks delivery counts, and honours
the same idle window. A double that simply hands back messages would make dev and CI a more
forgiving world than production, and every bug in this list would be found in production
first.

## Turning an order event into a notification

**NTF-202** registers the first handler on that framework. Commerce publishes either
`order.confirmed` or `order.status_changed` -- never both for the same move -- and both route
to the same consumer, because to a user they are the same thing: the order moved.
`order.created` is deliberately **left unregistered**; placing an order is not news to the
person who just placed it, and the absence is visible in `events/factory.py` rather than
buried in a handler that quietly does nothing.

### Each status maps to one notification type

| order status | notification type |
| --- | --- |
| `confirmed` | `order_confirmed` |
| `preparing` | `order_preparing` |
| `in_transit` | `order_in_transit` |
| `delivered` | `order_delivered` |
| `cancelled` | `order_cancelled` |
| `pending` | none -- not news |

A status this build has never heard of raises `UnknownOrderStatus`, which the dispatcher parks.
That is the **opposite** of its treatment of an unknown event *type*, and deliberately so: a new
type is routine producer growth, whereas a new status on an event we already handle is a rare,
deliberate change to the order lifecycle -- exactly what a dead-letter queue is for.

### The progress mark, and why it ranks cancellation last

Streams redeliver and reorder. A `preparing` event arriving after `delivered` must not tell the
user their food is being cooked, so the consumer keeps a **monotonic mark** per order --
`OrderProgressStore`, one key per order, holding the *rank* of the furthest status announced.
`advance` only ever moves it forward; in Redis that is a Lua script, because a read-then-write
would let two workers each see the old value. An event at or behind the mark is dropped.

`PROGRESS` ranks `cancelled` **above** `delivered`. That is not Commerce's state machine -- it
is a notification ordering, and it encodes that "your order was cancelled" is the last word on
an order regardless of what raced in behind it.

The mark outlives a realistic order (`NOTIFICATION_ORDER_PROGRESS_TTL_SECONDS`, 7 days) and is
asserted to be longer than the dedupe window: a mark that expired first would let a late
redelivery re-announce a status the user has already seen.

### Read the guard, record, then advance -- in that order

`handle` reads the mark, records the notification, and *only then* advances. Advancing first
and treating "it moved" as permission to notify would lose the notification permanently if the
recorder then failed -- the mark would already say the user had been told. Reading first means
a crash leaves the mark **behind**, the event is redelivered, and NTF-103's dedupe absorbs the
duplicate. The mark is advanced for **every** non-exception outcome, including a duplicate and
a preference-suppressed delivery, because it tracks what we have *decided about*, not what we
managed to tell the user.

### What the client gets

The payload carries `orderId`, `status`, `occurredAt`, and `previousStatus` when the event
named a prior state. The status *values* are Commerce's own vocabulary, unaltered -- only the
keys are renamed from the event's `toStatus`/`fromStatus` to what a client reading a
notification would expect. There is no title or body: copy is localized on the client, and a
Spanish user should not receive English text baked in at write time.

`created_at` is the moment we record, **not** the event's `occurredAt`. Back-dating a replayed
event would file it under a day the user has already scrolled past, so the original instant
travels in the payload instead, where a client can render "2 hours ago" if it wants to.



Liveness (`/health`) answers "is the process up?"; readiness (`/health/ready`) answers "can
it actually do its job?", and reports a named check per dependency so operators can see
*why* a pod is out of rotation:

| check | satisfied by | when unconfigured |
| --- | --- | --- |
| `redis` | `NOTIFICATION_REDIS_URL` | warn outside production, fail in production |
| `event_bus` | `NOTIFICATION_EVENT_BUS_URL`, else the Redis URL | warn outside production, fail in production |
| `push_providers` | FCM *or* APNs credentials, or `NOTIFICATION_PUSH_ENABLED=false` | warn outside production, fail in production |

A dependency that is *configured but unreachable* fails in every environment -- that is an
outage, not a missing local setup. A bare checkout therefore boots and serves, while a
production pod with nothing wired stays out of rotation.

The bus defaults to the same Redis as the datastore, so one container backs both locally;
splitting them in production stays a config change rather than a code change. The stream
name must match the commerce service's `COMMERCE_EVENT_STREAM` (COM-109).

## Testing

All builds/tests run in Docker.

```sh
# Unit suite (no infrastructure needed; the live-Redis legs skip)
docker build --target test -t nutriplan-notification-test services/notification
docker run --rm nutriplan-notification-test

# CI-parity run (real Redis + the mounted contract, so the Redis half of the store
# contract and the OpenAPI drift tests all run instead of skipping)
cd infra && docker compose --profile test run --rm --build notification-test

# Run the service
cd infra && docker compose up --build notification
curl -fsS http://localhost:8084/health/ready
```

The store contract suite is parametrized over **both** adapters, so every test in it is an
expectation the in-memory and Redis stores must both satisfy. An in-memory stand-in checked
only against itself proves nothing about production; this is what keeps the two from
drifting -- it is how we caught the Redis adapter leasing records from write time instead of
from creation time. The deduplication store and the recorder are held to the same standard.

The dedupe expiry tests really sleep for a second rather than injecting a clock. Injecting
one would be faster but would only prove the in-memory adapter's arithmetic; Redis expires
keys on its own clock, and whether the two agree is the entire question.

`NOTIFICATION_TEST_REDIS_URL` is deliberately a different variable from
`NOTIFICATION_REDIS_URL`: it points the store and probe suites at a live server without
changing what the service itself is configured with, so the tests asserting on an
unconfigured service still hold. It is skipped when unset locally and required under `CI`.
