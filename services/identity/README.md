# Identity Service

**Bounded context:** Identity. Authentication, OAuth (Google/Facebook/Apple), JWT issuance,
user profile, and dietary preferences.

- **Stack:** Python 3.12 · FastAPI · SQLAlchemy 2.0 · Alembic · PostgreSQL
  ([ADR 0004](../../docs/architecture/adr/0004-backend-service-framework.md))
- **API contract:** [`contracts/identity.openapi.yaml`](../../contracts/identity.openapi.yaml)
- **Local port:** `8081`

> 🐳 **Everything runs in Docker** — no host-level `pip install`. Build/test/run via the image
> and `docker compose`.

## Layout

```
app/
  main.py            # FastAPI app + router wiring
  core/config.py     # IDENTITY_-prefixed settings
  core/security.py   # Argon2id hashing, RS256 JWT issue/verify, JWKS
  core/errors.py     # RFC 7807 problem+json error handlers (IDN-106)
  core/ratelimit.py  # per-IP/route rate-limit middleware (IDN-106)
  core/oauth.py      # Google/Apple id-token verification + verified-email dedupe (IDN-201/202/204)
  db/base.py         # engine + session + Base
  db/models.py       # users, credentials, refresh_tokens, oauth_identities (IDN-101)
  schemas/           # request/response models (camelCase, matches the contract)
  services/auth_service.py     # register / login (+lockout) / refresh (rotation + reuse-detection)
  services/profile_service.py  # profile + dietary-preference updates (IDN-301/302/303)
  api/               # health, jwks, auth, users routers + auth dependency
alembic/             # migrations (IDN-101)
tests/               # pytest suite (unit + API)
```

## Endpoints

| Method | Path | Story | Notes |
| --- | --- | --- | --- |
| `POST` | `/auth/register` | IDN-102 | Argon2id hashing → `201 AuthResponse`; dup email → `409`, weak password → `422` |
| `POST` | `/auth/login` | IDN-103 | credential verify + failed-attempt lockout (`429 + Retry-After`) |
| `POST` | `/auth/refresh` | IDN-105 | refresh rotation + reuse-detection (family revoke → `401`) |
| `POST` | `/auth/oauth/{provider}` | IDN-201/202/204 | verify Google/Apple id-token (`aud`/`iss`/`exp`, Apple `nonce`) → auto-provision, or **dedupe/link to an existing account by verified email**; unverified-email collision → `409`; bad token → `401` |
| `GET`  | `/users/me` | IDN-301 | Bearer-guarded profile incl. `dietaryPreferences` |
| `PUT`  | `/users/me` | IDN-302 | update `name` / `avatarUrl` (partial; validated) |
| `PUT`  | `/users/me/dietary-preferences` | IDN-303 | dietType / allergies / calories / macros / cuisines (enums + ranges; partial-merge, round-trips through `/users/me`) |
| `GET`  | `/.well-known/jwks.json` | IDN-104/802 | public JWKS for token verification by other services |
| `GET`  | `/health` | — | liveness probe |

JWT access tokens are RS256 with a `kid` header and `sub`/`email`/`exp` claims (IDN-104).

**Errors & abuse protection (IDN-106):** every `4xx`/`5xx` is returned as
`application/problem+json` (RFC 7807). Requests are rate-limited per client IP — `/auth/*`
gets a stricter budget — and exceeding it yields `429` + `Retry-After`.

## Run (Docker)

From `infra/`:

```bash
docker compose up --build identity      # starts postgres + identity on :8081 (runs migrations first)
curl -s localhost:8081/health
```

## Test (Docker)

```bash
# Fast, no external DB — SQLite inside the test image:
docker build --target test -t nutriplan-identity-test ../services/identity
docker run --rm nutriplan-identity-test

# Faithful — against Postgres via compose:
docker compose --profile test run --rm identity-test
```

## Configuration (`IDENTITY_` env vars)

| Var | Default | Purpose |
| --- | --- | --- |
| `IDENTITY_DATABASE_URL` | `postgresql+psycopg://nutriplan:nutriplan@postgres:5432/identity` | SQLAlchemy URL |
| `IDENTITY_JWT_PRIVATE_KEY` / `IDENTITY_JWT_PUBLIC_KEY` | _(empty → ephemeral dev key)_ | RS256 PEM keys (inject from the secrets manager in stage/prod — IDN-803) |
| `IDENTITY_JWT_KID` | `nutriplan-dev` | key id published in the JWKS |
| `IDENTITY_ACCESS_TOKEN_TTL_SECONDS` | `900` | access-token lifetime |
| `IDENTITY_REFRESH_TOKEN_TTL_SECONDS` | `1209600` | refresh-token lifetime (14 d) |
| `IDENTITY_LOGIN_MAX_FAILED_ATTEMPTS` | `5` | failures before lockout |
| `IDENTITY_LOGIN_LOCKOUT_SECONDS` | `900` | lockout window |
| `IDENTITY_RATE_LIMIT_ENABLED` | `true` | toggle per-IP rate limiting (IDN-106) |
| `IDENTITY_RATE_LIMIT_DEFAULT_PER_MINUTE` | `120` | per-IP budget for non-auth routes |
| `IDENTITY_RATE_LIMIT_AUTH_PER_MINUTE` | `20` | per-IP budget for `/auth/*` routes |
| `IDENTITY_GOOGLE_CLIENT_IDS` | _(empty)_ | comma-separated Google OAuth client IDs accepted as `aud` (IDN-201) |
| `IDENTITY_APPLE_CLIENT_IDS` | _(empty)_ | comma-separated Apple service/bundle IDs accepted as `aud` (IDN-202) |
