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
persist and can be listed per user. Nothing is *delivered* yet -- the bus consumer arrives
in NTF-201/202, push delivery in NTF-301, and the in-app feed API in NTF-105.

## Layout

```
app/
  domain/enums.py       # notification type, channel, delivery status
  domain/notification.py# the immutable Notification record
  domain/repositories.py# the persistence port
  adapters/codec.py     # JSON record <-> Notification
  adapters/keys.py      # the Redis key scheme
  adapters/retention.py # the age + length window both stores enforce
  adapters/redis_notification_repository.py
  adapters/in_memory_notification_repository.py
  adapters/factory.py   # picks the store from configuration
  core/config.py        # NOTIFICATION_-prefixed settings (Redis, bus, push providers)
  core/readiness.py     # pure, environment-aware readiness evaluation
  core/probes.py        # the only place that opens a real connection
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

# CI-parity run (real Redis, so the Redis half of the store contract runs instead of skipping)
cd infra && docker compose --profile test run --rm --build notification-test

# Run the service
cd infra && docker compose up --build notification
curl -fsS http://localhost:8084/health/ready
```

The store contract suite is parametrized over **both** adapters, so every test in it is an
expectation the in-memory and Redis stores must both satisfy. An in-memory stand-in checked
only against itself proves nothing about production; this is what keeps the two from
drifting -- it is how we caught the Redis adapter leasing records from write time instead of
from creation time.

`NOTIFICATION_TEST_REDIS_URL` is deliberately a different variable from
`NOTIFICATION_REDIS_URL`: it points the store and probe suites at a live server without
changing what the service itself is configured with, so the tests asserting on an
unconfigured service still hold. It is skipped when unset locally and required under `CI`.
