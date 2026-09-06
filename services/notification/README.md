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
[`contracts/notification.openapi.yaml`](../../contracts/notification.openapi.yaml). Nothing
is *delivered* yet: the bus consumer arrives in NTF-201/202 and push delivery in NTF-301, so
today the feed only returns what a test or a direct writer has recorded.

## Layout

```
app/
  domain/enums.py       # notification type, channel, delivery status
  domain/notification.py# the immutable Notification record
  domain/dedupe.py      # the deterministic (event, user, type) key
  domain/repositories.py# the persistence and deduplication ports
  application/notification_recorder.py  # the idempotent write path
  application/feed.py     # the paged feed query, badge count, and mark-read use cases
  adapters/codec.py     # JSON record <-> Notification
  adapters/keys.py      # the Redis key scheme
  adapters/retention.py # the age + length window both stores enforce
  adapters/idempotency.py  # the replay window + provisional claim length
  adapters/redis_notification_repository.py
  adapters/in_memory_notification_repository.py
  adapters/redis_deduplication_store.py
  adapters/in_memory_deduplication_store.py
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

## Dependencies and readiness

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
