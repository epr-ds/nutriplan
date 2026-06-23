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
