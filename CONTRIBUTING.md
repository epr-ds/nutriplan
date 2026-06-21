# Contributing to NutriPlan

Thanks for helping build NutriPlan. This guide covers our workflow, conventions, and quality bar.

## Branching model

We use **trunk-based development** with short-lived feature branches off `main`.

- `main` is always releasable and protected (PR + green CI required).
- Branch naming: `<type>/<short-description>` — e.g. `feat/meal-plan-detail`, `fix/auth-refresh`.
- Keep branches small and focused; rebase on `main` before requesting review.

## Commit messages — Conventional Commits

```
<type>(<scope>): <subject>

[optional body]
[optional footer]
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`.
**Scopes (examples):** `mobile`, `identity`, `dietary`, `commerce`, `notification`, `ai`,
`contracts`, `infra`.

Examples:
```
feat(dietary): add meal plan nutritional summary endpoint
fix(mobile): refresh JWT before expiry on cold start
ci(mobile): cache Gradle dependencies
```

## Pull requests

1. Fill out the PR template (what / why / how tested).
2. Ensure all CI checks pass (build, tests, lint, CodeQL).
3. Keep the OpenAPI contract in `contracts/` in sync with any API change — **the contract is
   the source of truth**.
4. At least one approving review from a CODEOWNER is required.
5. Squash-merge; the PR title becomes the squash commit (use Conventional Commit style).

## Code style & quality

| Area | Tooling | Command |
|------|---------|---------|
| Kotlin | detekt + ktlint (via detekt formatting) | `cd mobile && ./gradlew detekt` |
| Python | ruff (lint + format) | `cd services/ai && ruff check . && ruff format --check .` |
| Contracts | Spectral | `npx @stoplight/spectral-cli lint "contracts/*.openapi.yaml"` |

- **Definition of Done:** reviewed, tested (unit + contract where relevant), telemetry added,
  contract in sync, accessibility considered, behind a feature flag when risky.
- Target ≥ 70% coverage on `domain`/`usecase` layers.

## Architecture guardrails

- Mobile follows **Clean Architecture**: `presentation → domain → data`. DTOs carry **no**
  business logic; domain models own behavior; mappers live at the boundary.
- Backend services are **independently deployable**; cross-service calls go through the API
  gateway or async events — never a shared database.
- New design decisions are captured as an **ADR** in `docs/architecture/adr/`.

## Local setup

See [README.md](README.md#getting-started).
