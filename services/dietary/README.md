# Dietary Planning Service

**Bounded context:** Dietary Planning. Meal plans, recipe repository, nutrition calculation,
and orchestration of AI requests.

- **Stack:** Python 3.12 · FastAPI · PyMongo (sync) · MongoDB
  ([ADR 0004](../../docs/architecture/adr/0004-backend-service-framework.md))
- **API contract:** [`contracts/dietary.openapi.yaml`](../../contracts/dietary.openapi.yaml)
- **Companion:** delegates AI work to [`services/ai`](../ai)
- **Local port:** `8082`

> 🐳 **Everything runs in Docker** — no host-level `pip install`. Build/test/run via the image
> and `docker compose`.

## Layout

```
app/
  main.py                # FastAPI app + lifespan (ensures the meal_plans collection on boot)
  core/config.py         # DIETARY_-prefixed settings (Mongo URL/db/timeout)
  domain/meal_plan.py    # MealPlan aggregate root + embedded PlannedMeal, enums, (de)serialization
  db/mongo.py            # PyMongo client/db accessors, $jsonSchema validator, index installer
  repositories/meal_plan_repository.py   # owner-scoped insert/get for the aggregate
  api/health.py          # /health liveness probe
tests/                   # pytest suite (health + repository + schema-validation + indexes)
```

## DPL-101 — MealPlan aggregate

This slice establishes the Dietary persistence foundation; HTTP endpoints land in later slices
(DPL-102+). The bounded context is organised around a single aggregate root, **`MealPlan`**, which
**owns** its embedded `PlannedMeal` items — a plan and its meals form one consistency boundary and
are stored as a single `meal_plans` document. Cross-aggregate references (the owning user, recipes)
are held **by id only**.

**Schema validation on write.** Every write to `meal_plans` is checked against a MongoDB
`$jsonSchema` validator (`app/db/mongo.py`) enforcing required fields, BSON types, and the
`status` / `mealType` / `dietaryType` enum domains. Invalid documents are rejected with a
`WriteError` (code 121). The validator is installed idempotently on startup (`create_collection`
or `collMod`), so it is safe to boot repeatedly.

**Indexes** (all owner-scoped, installed on startup):

| Name | Keys | Serves |
| --- | --- | --- |
| `userId_1` | `userId` | list a user's plans |
| `userId_status` | `userId`, `status` | filter a user's plans by lifecycle state |
| `userId_dateRange` | `userId`, `startDate`, `endDate` | date-range queries within a user's plans |

Dates (`startDate`/`endDate`) and timestamps (`createdAt`/`updatedAt`) are persisted as ISO-8601
**strings** — their lexicographic order is chronological, so the date-range index stays
range-queryable and we avoid the `datetime.date` → BSON gap (PyMongo stores `datetime`, not `date`).

## Endpoints

| Method | Path | Story | Notes |
| --- | --- | --- | --- |
| `GET` | `/health` | — | liveness probe |

> Meal-plan REST endpoints (create/list/get + state machine) arrive in DPL-102+ and are defined in
> [`contracts/dietary.openapi.yaml`](../../contracts/dietary.openapi.yaml).

## Run (Docker)

From `infra/`:

```bash
docker compose up --build dietary      # starts mongo + dietary on :8082
curl -s localhost:8082/health
```

## Test (Docker)

```bash
# Build the test image:
docker build --target test -t nutriplan-dietary-test ../services/dietary

# Faithful — against MongoDB via compose (one-shot):
docker compose --profile test run --rm dietary-test
```

There is no embedded/in-process MongoDB, so the Mongo-backed tests **skip** when no database is
reachable (a bare `docker run nutriplan-dietary-test` still passes the Mongo-free health tests).
CI and compose always provide a `mongo` service, so the full suite runs there. To run the full
suite against an ad-hoc Mongo container on a shared network:

```bash
docker network create dpl-net
docker run -d --name dpl-mongo --network dpl-net mongo:7
docker run --rm --network dpl-net \
  -e DIETARY_MONGO_URL=mongodb://dpl-mongo:27017 -e DIETARY_MONGO_DB=dietary_test \
  nutriplan-dietary-test sh -c "ruff check . && ruff format --check . && pytest -q"
```

The schema-validation tests insert **raw dicts** (bypassing Pydantic) to exercise the database
`$jsonSchema` validator directly; the index tests assert the three expected indexes exist.

## Configuration (`DIETARY_` env vars)

| Var | Default | Purpose |
| --- | --- | --- |
| `DIETARY_MONGO_URL` | `mongodb://nutriplan:nutriplan@mongo:27017/?authSource=admin` | MongoDB connection string (root creds live in the `admin` DB → `authSource=admin`) |
| `DIETARY_MONGO_DB` | `dietary` | database name (tests/CI use `dietary_test`) |
| `DIETARY_MONGO_SERVER_SELECTION_TIMEOUT_MS` | `5000` | how long PyMongo waits for a reachable server before erroring |
| `DIETARY_ENVIRONMENT` | `development` | environment label |
