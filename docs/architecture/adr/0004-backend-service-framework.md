# 4. Backend services on Python + FastAPI

- Status: Accepted
- Date: 2026-06-20

## Context

The backend is a set of bounded-context services (identity, dietary, commerce, notification,
ai) that communicate over HTTP. Each service's public surface is defined by an OpenAPI contract
under `contracts/` — the contract, not the implementation language, is the integration source of
truth.

The mobile client is Kotlin Multiplatform (ADR 3). The `services/identity` README originally left
the service stack as an open decision ("Framework TBD — JVM, e.g. Kotlin + Ktor vs. Spring Boot"),
with the implicit appeal of "Kotlin everywhere". Two facts pushed against that default:

1. The first service to ship, **`services/ai`, is already Python + FastAPI** (Dockerfile, ruff,
   pytest). A second language would fork our CI, tooling, and shared-library story on day one.
2. The development and CI environment is **container-first with no local JVM toolchain**. All
   build/test/run happens inside Docker images; a fast Python inner loop is materially cheaper to
   operate than a Dockerised Gradle/JVM loop.

## Decision

All backend services are built with **Python 3.12 + FastAPI**, and **everything runs in Docker**
(no host-level dependency installation):

- **Web framework:** FastAPI + Uvicorn. **Validation/serialization:** Pydantic v2 +
  pydantic-settings (env-prefixed config, one prefix per service, e.g. `IDENTITY_`).
- **Persistence:** SQLAlchemy 2.0 + Alembic migrations for PostgreSQL services; the driver is
  `psycopg` (v3).
- **Security primitives** (identity): Argon2id password hashing (`argon2-cffi`), RS256 JWT
  issue/verify with a published JWKS (`pyjwt[crypto]`).
- **Quality gate:** `ruff` (lint + format) and `pytest`, run as a per-service job in Backend CI.
- **Packaging:** a multi-stage `Dockerfile` per service (`runtime` target for the deployable
  image, `test` target carrying dev deps + tests). The container is the unit of build, test, and
  deploy; contributors do not `pip install` on the host.

This supersedes the "JVM service stack" note in `services/identity/README.md`.

## Consequences

- One backend language, one toolchain, one CI pattern across every service; `services/ai` is the
  reference implementation and new services mirror it.
- The mobile app and backend no longer share domain models in source; they share the **OpenAPI
  contracts** instead, which is the boundary we already treat as authoritative. Cross-language
  model drift is caught by contract/integration tests rather than the compiler.
- Container-first means a clean, reproducible environment and no "works on my machine" host
  drift — at the cost of a Docker dependency for every build/test invocation (acceptable and, in
  this environment, required).
- We forgo the Spring Security / Spring ecosystem; for identity we assemble equivalent building
  blocks (Argon2id, PyJWT/JWKS, SQLAlchemy/Alembic) explicitly. These are mature and well
  understood.
- If a future service has hard requirements better served by the JVM (or another runtime), that is
  a new, scoped ADR — this decision is the default, not a prohibition.
