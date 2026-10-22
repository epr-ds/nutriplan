# Commerce Service

**Bounded context:** Commerce. Orders, fulfillment (dark kitchen / grocery), external
provider integration (FreshBasket/Walmart/Chedraui), and payments (cards, PayPal, OXXO, SPEI).

- **Framework:** Python 3.12 · FastAPI (per ADR 0004)
- **Datastore:** PostgreSQL (SQLAlchemy 2.0 + Alembic)
- **API contract:** [`contracts/commerce.openapi.yaml`](../../contracts/commerce.openapi.yaml)
- **Port:** 8083
- **Integration:** external providers sit behind an anti-corruption layer with circuit breakers.

## Status

Phase 4 in progress. **COM-101** delivered the persistence foundation: the `Order` aggregate
(with `OrderItem`s, a delivery `Address`, and a `Money` value object) and its Postgres schema —
`addresses`, `orders`, `order_items` — with owner-scoped indexes on `orders.user_id`,
`orders.status` and `orders.created_at`. Only `/health` + `/health/ready` are exposed so far;
order endpoints arrive in COM-102+.

## Layout

```
app/
  core/config.py        # COMMERCE_-prefixed settings
  db/base.py            # engine, session, declarative Base
  db/models.py          # ORM: AddressModel, OrderModel, OrderItemModel
  domain/               # Money, enums, Address, Order aggregate, repository port
  repositories/         # SqlOrderRepository (adapter for the port)
  api/                  # deps, schemas (OrderResponse projection), health, router
alembic/                # migration env + versions (0001_initial)
tests/                  # pytest (SQLite by default; Postgres in CI/compose)
```

## Testing

All builds/tests run in Docker. Tests default to a throwaway SQLite file; CI and the
`commerce-test` compose service point `COMMERCE_DATABASE_URL` at Postgres.

```sh
# Unit/integration suite (SQLite, in-image)
docker build --target test -t nutriplan-commerce-test services/commerce
docker run --rm nutriplan-commerce-test

# CI-parity run (Postgres-backed, contract mounted for the drift-guard)
cd infra && docker compose --profile test run --rm --build commerce-test
```

### Ephemeral test environment (COM-801)

`COMMERCE_TEST_DB=postgres` brings up a clean, throwaway Postgres (`postgres:16-alpine`) through
Testcontainers for the run and removes it afterwards. It needs only a Docker daemon, with no
hand-managed server and no `COMMERCE_DATABASE_URL`. If the container can't be started the run fails
instead of falling back to SQLite. The `Commerce ephemeral Postgres (Testcontainers)` CI job runs
the whole suite this way.

```sh
cd services/commerce
pip install -r requirements-dev.txt
COMMERCE_TEST_DB=postgres pytest
```

Seed and teardown helpers live in `tests/seed.py`:
- `seed_orders` stores a pending dark-kitchen order and a confirmed grocery order (FreshBasket) for
  `SEED_USER_ID`.
- `seed_payment_methods` stores a saved Visa card and a PayPal wallet for `SEED_USER_ID`.
- Both are also available as the `seeded_orders` / `seeded_payment_methods` fixtures, and write
  through the service's own SQL repositories.
- `create_schema` / `drop_schema` rebuild the tables (the autouse fixture runs them around every
  test).
- `clear_data` empties every table while keeping the schema.

The fixtures `db_source` (`testcontainers`, `env` or `sqlite`) and `db_backend` (`postgres` or
`sqlite`) say which database a run is using. `tests/test_harness.py` covers the harness itself, plus
an integration pass through the real API and repositories that checks the responses against
`contracts/commerce.openapi.yaml`.
