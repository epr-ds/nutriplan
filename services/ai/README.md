# AI Service

Recommendations, meal analysis, and plan optimization for the Dietary Planning context.
**Python · FastAPI · LLM.**

## Endpoints (current scaffold)
- `GET /` — service info
- `GET /health` — **liveness** probe (is the process up?) → always `200 {"status":"ok"}`
- `GET /health/ready` — **readiness** probe (can it serve AI traffic?) → `200` when ready,
  `503` when not; the body lists each dependency check (`name`/`status`/`detail`).

Domain endpoints (`/ai/recommendations`, `/ai/analyze-meal`, `/ai/optimize-plan`) are defined
in [`contracts/dietary.openapi.yaml`](../../contracts/dietary.openapi.yaml) and implemented in
Phase 3 (AIA-201+).

### Liveness vs readiness (AIA-101)
The two probes are deliberately separate so an orchestrator **restarts** a dead pod but only
**withholds traffic** from a live-but-unconfigured one. Readiness is a pure function of config
(`app/core/readiness.py`) and is **environment-aware**:

| Condition | `llm_provider` check | Ready? |
| --- | --- | --- |
| `AI_LLM_API_KEY` set | `ok` | yes (`200`) |
| key missing, non-production | `warn` | yes (`200`) — dev/CI still come up |
| key missing, `AI_ENVIRONMENT=production` | `fail` | **no** (`503`) — out of rotation |

## LLM provider abstraction (AIA-102)
`app/llm/` is the single seam between the service and any hosted LLM — the rest of the codebase
depends only on the `LLMProvider` **port** and the vendor-neutral value objects, never on a
vendor SDK. It is consumed by the `/ai/*` endpoints starting in AIA-201.

```
LLMRequest -> LLMClient (retries + backoff) -> LLMProvider (port) -> OpenAI | Anthropic | Fake
                                                                       └─> LLMResponse
```

- **Port + adapters.** `LLMProvider.complete(request) -> LLMResponse` is implemented by
  `OpenAIProvider` and `AnthropicProvider` (real `httpx`, each mapped to its vendor wire format)
  and by `FakeLLMProvider` (scripted, network-free) for tests and offline dev. Vertex is a
  recognized provider name but its adapter is pending (it needs GCP service-account creds, not a
  plain API key), so the factory fails loudly rather than degrading silently.
- **Resilience.** `LLMClient` wraps any provider and retries only **transient** failures
  (`429`, `5xx`, timeouts, transport blips) with **exponential backoff + full jitter**, bounded
  by `AI_LLM_MAX_RETRIES`. Terminal failures (auth, bad request, malformed response) propagate
  on the first attempt. Per-call timeouts come from `AI_LLM_TIMEOUT_SECONDS`.
- **Selection.** `build_client(settings)` picks the adapter from `AI_LLM_PROVIDER` and wires the
  retry budget, so callers ask for a client without hard-coding a vendor.
- **Secrets.** The API key is sent only as a request header and never appears in a log line, an
  exception message, or a provider's `repr` (AIA-102 / AIA-802). Adapters are tested offline with
  `httpx.MockTransport`, including assertions that the key never leaks.

## Prompt templating (AIA-103)
`app/prompts/` makes prompts first-class instead of string literals buried in the endpoints:
each is **templated**, **versioned**, and **localized** (`es`/`en`), and every render **records
which prompt version ran** so completions stay attributable. Like `app/llm/`, it is foundation —
consumed by the `/ai/*` endpoints from AIA-201 — and it never imports a provider; it only produces
the `LLMMessage` sequence a request is built from.

```
PromptRenderer.render(id, locale, variables)
   -> PromptCatalog.get(id, locale)   # locale-aware, falls back to the default locale
   -> PromptTemplate.render(variables)# $variable substitution -> system/user messages
   -> PromptTelemetry.record(ref)     # id + version + locale, on every call
   -> RenderedPrompt.to_request(...)  # bridge to app/llm (LLMRequest)
```

- **Templates with variables.** `PromptTemplate` holds a `system`/`user` body using
  `string.Template` `$variable` placeholders (chosen over `str.format` so literal braces in JSON or
  code examples are safe). A missing variable raises rather than leaking `$placeholder` text; extra
  variables are ignored; non-string values are stringified.
- **Versioning + telemetry.** Each template carries an `id` + `version`; `PromptRenderer` records a
  `PromptRef` (id, version, locale) through the `PromptTelemetry` port on every render. Only those
  identifiers are recorded — never the rendered text or variable values, which may contain user data.
- **Locale-aware (es/en).** Templates are registered per locale in a `PromptCatalog`; lookup matches
  the requested locale and **falls back to the default locale** (`en`) when one is missing, so an
  unexpected language degrades to a working prompt. `Locale.parse` normalizes tags like `es-MX`/`en_US`.
- **Ports + DI.** `PromptCatalog` and `PromptTelemetry` are injected, so tests use in-memory doubles
  and production wires the shipped catalog (`build_default_renderer()`) plus a logging recorder. The
  seed catalog ships a versioned `meal_recommendation` prompt in both locales.

## Structured outputs (AIA-104)
`app/structured/` makes a `/ai/*` response *conform to its schema* a property of the call rather
than a hope. A Pydantic model — the same kind FastAPI turns into the OpenAPI schema — is the single
source of truth: it both **constrains** the provider and **validates** the reply, and a completion
that fails validation is **retried or falls back** instead of returning malformed data.

```
StructuredCompletion.complete(request)
   -> attach ResponseFormat (model JSON schema)   # AC1: constrain the provider
   -> LLMClient.complete(...)                      # transport retries live here
   -> StructuredOutputParser.parse(content)        # AC2: extract JSON + model_validate
   -> on StructuredOutputError: re-prompt & retry, # AC3: typed error -> retry...
      then fallback(error) or raise                #      ...or fallback
```

- **Constrained outputs (AC1).** `LLMRequest` carries an optional `ResponseFormat`; the OpenAI
  adapter emits it as a native `response_format: json_schema` and the Anthropic adapter as a **forced
  tool**, normalizing the returned `tool_use` block back into JSON text so callers parse content the
  same way regardless of provider. `to_strict_json_schema` tightens a model's schema (recursively sets
  `additionalProperties: false` and marks every property required) for strict structured-output modes.
- **Parsed + validated (AC2).** `StructuredOutputParser` isolates the JSON value (tolerating a stray
  code fence or sentence of prose), then validates it with `model_validate`. The result is a typed
  model instance or a typed error.
- **Invalid → typed error → retry or fallback (AC3).** `StructuredCompletion` raises
  `OutputParsingError`/`OutputValidationError`, re-prompts with the error up to `max_attempts`, and
  then calls an injected `fallback` (e.g. a curated recommendation) or re-raises. This is separate
  from `LLMClient`'s transport retries: one handles a bad *answer*, the other a bad *connection*.

Like `app/llm/` and `app/prompts/`, this is foundation — no HTTP route is added here; the `/ai/*`
endpoints consume it from AIA-201.

## Response caching + token budgets (AIA-105)
Repeated AI requests should be cheap *and* bounded, so completions are served from a cache
and gated by token quotas. Both sit behind one `KeyValueStore` port (`app/kv/`) — Redis in
production (`AI_REDIS_URL`), an in-process store in dev/CI/tests — so neither concern
imports a driver or assumes a server is running.

```
CachedCompletionService.complete(request, scope)
   -> ResponseCache.get(request)        # AC1: hit returns now, costs nothing
   -> TokenBudgetGuard.check(scope)      # AC2/AC3: refuse if quota spent / kill-switch on
   -> base.complete(request)             # provider runs once (with LLMClient retries)
   -> TokenBudgetGuard.charge(scope, usage.total_tokens)
   -> ResponseCache.put(request, response)
```

- **Cache keyed on a normalized request; configurable TTL (AC1).** `app/cache/` reduces a
  request to a canonical JSON string (model, sampling settings, ordered messages, and any
  response-format schema — recursively key-sorted) and stores the response under
  `sha256` of it for `AI_CACHE_TTL_SECONDS`. A corrupt or superseded entry is read as a
  miss, never an error.
- **Per-user / per-route token quotas (AC2).** `TokenBudgetGuard` (`app/budget/`) keeps a
  counter per `BudgetScope` (`user_id`, `route`) over a rolling window. `check` refuses a
  request whose window quota is already spent; `charge` records the call's real
  `total_tokens` afterward. Because cost is only known after the call, a single request may
  cross the line — the next one in that window is then refused (a soft quota). A limit of `0`
  disables that dimension, so quotas are opt-in.
- **Global budget kill-switch (AC3).** When `charge` pushes overall usage past
  `AI_BUDGET_GLOBAL_TOKENS`, a flag is **latched** for the rest of the window, so *every*
  caller — not just the one that tipped it over — is turned away until it rolls off. Counters
  and the flag expire via the store's TTL, so the window resets itself with no sweeper.

The cache is checked **before** the budget so a hit is free, and the guard records usage
**after** the call so quotas reflect real cost. Composition order is the point:
`build_cached_completion_service(base_client)` wires it from config. Like the rest of
`app/`, this is foundation — no HTTP route is added; the `/ai/*` endpoints consume it from
AIA-201.

## Configuration
12-factor: every value is environment-driven (prefix `AI_`, see `app/core/config.py`). Secrets
are injected at runtime, never baked into the image.

| Variable | Default | Purpose |
| --- | --- | --- |
| `AI_ENVIRONMENT` | `development` | `production`/`prod` makes missing deps fatal for readiness |
| `AI_LLM_PROVIDER` | `openai` | LLM provider id |
| `AI_LLM_API_KEY` | _(empty)_ | provider secret (AIA-802); drives the readiness check |
| `AI_LLM_MODEL` | `gpt-4o-mini` | default model (used by the AIA-102 client) |
| `AI_LLM_TIMEOUT_SECONDS` | `30.0` | per-call timeout (AIA-102) |
| `AI_LLM_MAX_RETRIES` | `2` | retry budget (AIA-102) |
| `AI_REDIS_URL` | _(empty)_ | Redis URL backing the cache + budgets (AIA-105); blank uses an in-process store |
| `AI_CACHE_ENABLED` | `true` | toggle response caching (AIA-105) |
| `AI_CACHE_TTL_SECONDS` | `3600` | cached-response lifetime (AIA-105) |
| `AI_BUDGET_ENABLED` | `true` | toggle token quotas + kill-switch (AIA-105) |
| `AI_BUDGET_WINDOW_SECONDS` | `86400` | quota window over which counters reset (AIA-105) |
| `AI_BUDGET_PER_USER_TOKENS` | `0` | per-user token quota per window; `0` = unlimited (AIA-105) |
| `AI_BUDGET_PER_ROUTE_TOKENS` | `0` | per-route token quota per window; `0` = unlimited (AIA-105) |
| `AI_BUDGET_GLOBAL_TOKENS` | `0` | global token budget / kill-switch; `0` = unlimited (AIA-105) |

## Run & test (Docker-first)
The repo is built container-first — no host Python installs required.

```bash
# from infra/ — one-shot test runner (ruff + pytest live in the test image)
docker compose --profile test run --rm ai-test

# run the service
docker compose up ai            # serves on http://localhost:8000
```

Iterate on the test image directly (mount the source so edits need no rebuild):

```bash
# from services/ai/
docker build --target test -t nutriplan-ai-test .
docker run --rm -v "$PWD:/app" -w /app nutriplan-ai-test \
  sh -c "ruff format --check . && ruff check . && pytest -q"
```

## Quality
```bash
ruff check .
ruff format --check .
pytest
```
