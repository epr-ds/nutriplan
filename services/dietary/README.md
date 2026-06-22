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

The service is organised in layers (Domain-Driven / Ports & Adapters). Dependencies point
**inward**: the API depends on the application service, which depends on the domain and on a
repository **port** — never on MongoDB directly.

```
app/
  main.py                # FastAPI app + lifespan + exception-handler registration
  domain/                # Pure business model — no framework/IO imports
    meal_plan.py         #   MealPlan aggregate root (+ MealPlan.create factory & invariants)
    recipe.py            #   Recipe aggregate root (+ Ingredient / NutritionalInfo value objects)
    repositories.py      #   MealPlanRepository + RecipeRepository ports (abstract)
    errors.py            #   DomainError hierarchy (e.g. MealPlanDateRangeError)
  application/           # Use cases (orchestration)
    commands.py          #   CreateMealPlanCommand (DTO; user_id comes from the principal)
    meal_plan_service.py #   MealPlanService.create_meal_plan(command)
  repositories/
    mongo_meal_plan_repository.py   # MongoDB adapter implementing the MealPlan port
    mongo_recipe_repository.py      # MongoDB adapter implementing the Recipe port
  db/
    mongo.py             #   PyMongo client/db accessors, $jsonSchema validators, index installers
    seed.py              #   Idempotent reference recipe catalog (DPL-201)
  core/
    config.py            #   DIETARY_-prefixed settings
    principal.py         #   Principal (authenticated caller)
    security.py          #   TokenVerifier port + JwtTokenVerifier (RS256 via Identity JWKS)
  api/
    deps.py              #   Composition root: wires verifier / principal / repo / service
    schemas.py           #   Request/response models (camelCase, match the contract)
    meal_plans.py        #   POST + GET (list) + GET /{id} + PATCH /{id} meal-plans router
    errors.py            #   DomainError -> HTTP mapping
    health.py            #   /health liveness probe
tests/                   # pytest suite (domain + application + security unit tests; API + Mongo)
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

## DPL-201 — Recipe catalog

The second aggregate root, **`Recipe`**, backs a shared recipe catalog that meal plans reference by
id (a `PlannedMeal.recipeId`). A recipe **owns** its embedded `Ingredient` lines and carries a
per-serving `NutritionalInfo`, all stored as a single `recipes` document. Unlike meal plans, recipes
are **not owner-scoped** — the catalog is global — so the `RecipeRepository` reads by recipe id alone.

**Schema validation on write.** `recipes` has its own `$jsonSchema` validator (`app/db/mongo.py`):
`_id`/`name`/`servings`/`ingredients`/`createdAt` are required, `servings` must be a positive `int`,
and every ingredient must carry a `name`. Installed idempotently on startup, like `meal_plans`.

**Indexes** (installed on startup) support the ingredient + macro filters used by recipe search
(DPL-202):

| Name | Keys | Serves |
| --- | --- | --- |
| `ingredientName` | `ingredients.name` (multikey) | find recipes containing an ingredient |
| `nutrition_calories` | `nutritionalInfo.calories` | filter/sort by per-serving calories |
| `nutrition_protein` | `nutritionalInfo.protein` | filter/sort by per-serving protein |
| `nutrition_carbs` | `nutritionalInfo.carbs` | filter/sort by per-serving carbs |
| `nutrition_fat` | `nutritionalInfo.fat` | filter/sort by per-serving fat |

**Reference seed.** `app/db/seed.py` upserts a small fixed-id catalog on startup so meal plans can
reference real recipes before any authoring UI exists. The seed uses stable ids and a fixed
timestamp, so re-running it (every boot) is a pure upsert — it never duplicates or churns rows.

## DPL-105 — Add a meal to a plan

`POST /meal-plans/{planId}/meals` adds a `PlannedMeal` (a recipe reference + `servings`) to the
caller's plan. The aggregate owns the only intrinsic rule — `servings > 0`
(`MealPlan.add_meal()` raises `InvalidServingsError` → `422`) — while the *existence* of the
referenced recipe is a cross-aggregate concern validated by the application layer.

Because this use case needs **both** the meal-plan and recipe repositories, it lives in a focused
**`MealService`** (`app/application/meal_service.py`) rather than widening `MealPlanService`, which
only depends on the plan repository. `add_meal_to_plan` loads the plan owner-scoped (missing or not
owned → `MealPlanNotFoundError` → `404`), resolves the recipe (unknown → `RecipeNotFoundError` →
`422`), mutates the aggregate, and persists it only on success. The `201 MealResponse` embeds the
resolved `RecipeResponse`; the plan detail/list projections leave `recipe` null (they don't fan out
to the catalog). Recomputing the plan-level `nutritionalSummary` is out of scope (DPL-302).

## Endpoints

| Method | Path | Story | Notes |
| --- | --- | --- | --- |
| `POST` | `/meal-plans` | DPL-102 | Create a draft meal plan scoped to the caller → `201 MealPlanResponse`. Requires a Bearer token; `endDate < startDate` → `422` |
| `GET` | `/meal-plans` | DPL-103 | List the caller's plans → `200 MealPlanSummaryResponse[]`. Requires a Bearer token. Query: `status` (active/completed/saved), `page` (≥1), `limit` (1–100); newest first |
| `GET` | `/meal-plans/{planId}` | DPL-104 | Get one plan with full detail (incl. meals) → `200 MealPlanResponse`. Requires a Bearer token; missing or not owned → `404` (no cross-user leakage) |
| `PATCH` | `/meal-plans/{planId}` | DPL-106 | Transition a plan's lifecycle status (`draft → active → completed/saved`) → `200 MealPlanResponse`. Body `{ status }` (active/completed/saved). Illegal transition → `409`; activating with no meals → `422`; missing or not owned → `404` |
| `POST` | `/meal-plans/{planId}/meals` | DPL-105 | Add a meal (a recipe reference + servings) to the caller's plan → `201 MealResponse` (with the embedded recipe). Body `{ mealType, recipeId, servings }`. Unknown recipe or `servings ≤ 0` → `422`; missing or not owned plan → `404` |
| `GET` | `/health` | — | liveness probe |

> Remaining meal-plan endpoints (list/get + state machine) arrive in DPL-103/104/106 and are defined
> in [`contracts/dietary.openapi.yaml`](../../contracts/dietary.openapi.yaml).

## Authentication (DPL-102)

The Dietary service is a **resource server**: it does not issue tokens, it verifies the RS256 access
tokens minted by the [Identity service](../identity). On each guarded request the
`JwtTokenVerifier` resolves the signing key from Identity's published JWKS
(`/.well-known/jwks.json`) by the token's `kid`, then validates the signature plus the
`aud` / `iss` / `exp` claims and projects `sub` onto a `Principal`. The endpoint takes the owning
`userId` from that principal — never from the request body — so plans are always scoped to the
caller. Missing/invalid/expired tokens yield `401`.

The verifier depends on an abstract signing-key resolver (PyJWT's `PyJWKClient` in production), so
its logic is unit-tested with a throwaway RSA key and **no network access**.

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
`$jsonSchema` validators directly; the index tests assert the expected `meal_plans` and `recipes`
indexes exist.

## Configuration (`DIETARY_` env vars)

| Var | Default | Purpose |
| --- | --- | --- |
| `DIETARY_MONGO_URL` | `mongodb://nutriplan:nutriplan@mongo:27017/?authSource=admin` | MongoDB connection string (root creds live in the `admin` DB → `authSource=admin`) |
| `DIETARY_MONGO_DB` | `dietary` | database name (tests/CI use `dietary_test`) |
| `DIETARY_MONGO_SERVER_SELECTION_TIMEOUT_MS` | `5000` | how long PyMongo waits for a reachable server before erroring |
| `DIETARY_IDENTITY_JWKS_URL` | `http://identity:8081/.well-known/jwks.json` | Identity service JWKS used to verify access tokens (DPL-102) |
| `DIETARY_JWT_ISSUER` | `nutriplan-identity` | required `iss` claim on access tokens |
| `DIETARY_JWT_AUDIENCE` | `nutriplan` | required `aud` claim on access tokens |
| `DIETARY_ENVIRONMENT` | `development` | environment label |
