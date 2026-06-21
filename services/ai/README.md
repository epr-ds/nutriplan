# AI Service

Recommendations, meal analysis, and plan optimization for the Dietary Planning context.
**Python · FastAPI · LLM.**

## Endpoints (current scaffold)
- `GET /` — service info
- `GET /health` — liveness probe

Domain endpoints (`/ai/recommendations`, `/ai/analyze-meal`, `/ai/optimize-plan`) are defined
in [`contracts/dietary.openapi.yaml`](../../contracts/dietary.openapi.yaml) and implemented in
Phase 3.

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

## Quality
```bash
ruff check .
ruff format --check .
pytest
```

## Configuration
Environment variables are prefixed with `AI_` (see `app/core/config.py`):
`AI_ENVIRONMENT`, `AI_LLM_PROVIDER`, `AI_LLM_API_KEY`.
