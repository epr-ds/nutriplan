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
No notification is stored or delivered yet -- the Redis store arrives in NTF-102, the bus
consumer in NTF-201/202, and push delivery in NTF-301.

## Layout

```
app/
  core/config.py        # NOTIFICATION_-prefixed settings (Redis, bus, push providers)
  core/readiness.py     # pure, environment-aware readiness evaluation
  core/probes.py        # the only place that opens a real connection
  api/health.py         # GET /health, GET /health/ready
  main.py               # FastAPI wiring
tests/                  # pytest
```

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
# Unit suite (no infrastructure needed; the live-Redis probe suite skips)
docker build --target test -t nutriplan-notification-test services/notification
docker run --rm nutriplan-notification-test

# CI-parity run (real Redis, so the probe suite runs instead of skipping)
cd infra && docker compose --profile test run --rm --build notification-test

# Run the service
cd infra && docker compose up --build notification
curl -fsS http://localhost:8084/health/ready
```

`NOTIFICATION_TEST_REDIS_URL` is deliberately a different variable from
`NOTIFICATION_REDIS_URL`: it points the probe suite at a live server without changing what
the service itself is configured with, so the tests asserting on an unconfigured service
still hold. It is skipped when unset locally and required under `CI`.
