# Regression Test Corpus

## HRD-901: Full Regression Suite Across P1–P5 Journeys

This directory contains the regression test corpus for each service.
Each service maintains its own `corpus.json` with test cases organized by journey.

### Corpus Format

```json
{
  "version": "1.0",
  "service": "ai",
  "last_updated": "2026-10-13",
  "cases": [
    {
      "name": "no-allergen-safety",
      "journey": "meal-analysis",
      "severity": "P0",
      "tags": ["regression", "safety", "allergen"],
      "description": "Verify no-allergen meals are correctly flagged",
      "input": {
        "meal": { "name": "Rice and Beans", "ingredients": [] },
        "allergen": "gluten"
      },
      "expected": {
        "warnings": ["Contains gluten"],
        "safe": false
      }
    }
  ]
}
```

### Severity Levels

| Severity | Meaning | Release Block |
|----------|---------|---------------|
| P0 | Safety-critical, data loss, security | YES |
| P1 | Core functionality broken | YES |
| P2 | Important feature broken | NO (warn) |
| P3 | Minor feature broken | NO |
| P4 | Edge case broken | NO |
| P5 | Cosmetic/optimization | NO |

### Service Corpora

#### AI Service (`services/ai/regression/corpus.json`)

| # | Name | Journey | Severity | Tags |
|---|------|---------|----------|------|
| 1 | no-allergen-safety | meal-analysis | P0 | regression, safety |
| 2 | allergen-family-expansion | meal-analysis | P0 | regression, safety |
| 3 | safe-recipe-passes | meal-analysis | P1 | regression |
| 4 | budget-constraint-met | optimization | P1 | regression |
| 5 | dietary-preferences-applied | optimization | P1 | regression |
| 6 | nutrition-targets-met | optimization | P2 | regression |
| 7 | recommendation-diversity | recommendations | P2 | regression |
| 8 | guardrails-compliance | meal-analysis | P0 | regression, safety, guardrails |
| 9 | prompt-injection-resistance | meal-analysis | P0 | regression, security |
| 10 | cache-fallback-behavior | meal-analysis | P2 | regression, performance |

#### Commerce Service (`services/commerce/regression/corpus.json`)

| # | Name | Journey | Severity | Tags |
|---|------|---------|----------|------|
| 1 | order-creation-idempotent | order-creation | P0 | regression, idempotency |
| 2 | payment-success-flow | payment | P0 | regression, payment |
| 3 | payment-failure-retry | payment | P1 | regression, payment |
| 4 | order-cancellation-refund | order-lifecycle | P1 | regression |
| 5 | slot-reservation-concurrency | slot-booking | P1 | regression, concurrency |
| 6 | grocery-provider-fallback | grocery | P2 | regression |
| 7 | voucher-application | pricing | P2 | regression |
| 8 | webhook-retry-delivery | webhook | P1 | regression, reliability |

#### Identity Service (`services/identity/regression/corpus.json`)

| # | Name | Journey | Severity | Tags |
|---|------|---------|----------|------|
| 1 | login-success | auth | P0 | regression |
| 2 | login-invalid-credentials | auth | P1 | regression |
| 3 | token-refresh-valid | auth | P1 | regression |
| 4 | token-refresh-expired | auth | P1 | regression |
| 5 | rate-limit-enforcement | auth | P1 | regression, security |
| 6 | profile-update-persist | profile | P2 | regression |
| 7 | oauth-callback-flow | oauth | P2 | regression |
| 8 | jwks-rotation | auth | P1 | regression, security |

#### Dietary Service (`services/dietary/regression/corpus.json`)

| # | Name | Journey | Severity | Tags |
|---|------|---------|----------|------|
| 1 | meal-plan-create | meal-plans | P1 | regression |
| 2 | meal-plan-get-current | meal-plans | P1 | regression |
| 3 | meal-plan-update-status | meal-plans | P2 | regression |
| 4 | recipe-search-by-ingredient | recipes | P2 | regression |
| 5 | recipe-search-by-dietary | recipes | P2 | regression |
| 6 | meal-nutrition-calculation | nutrition | P1 | regression |

#### Notification Service (`services/notification/regression/corpus.json`)

| # | Name | Journey | Severity | Tags |
|---|------|---------|----------|------|
| 1 | push-delivery-success | push | P1 | regression |
| 2 | push-delivery-failure-retry | push | P1 | regression, reliability |
| 3 | deduplication-window | push | P2 | regression |
| 4 | quiet-hours-enforcement | preferences | P2 | regression |
| 5 | dlq-replay | reliability | P1 | regression, reliability |
| 6 | meal-reminder-consumer | consumer | P2 | regression |

### Running the Suite

```bash
# Run all services
python regression/run.py --all

# Run specific services
python regression/run.py --services ai commerce

# Run with tag filter
python regression/run.py --services ai --tags regression

# Fail fast on P0/P1
python regression/run.py --all --fail-fast

# Generate JSON report
python regression/run.py --all --output regression/report-$(date +%Y%m%d).json
```

### CI Integration

Add to `.github/workflows/regression.yml`:

```yaml
  regression-suite:
    name: Full regression suite
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: '3.12'
      - name: Run full regression suite
        run: |
          pip install -r services/ai/requirements-dev.txt
          pip install -r services/commerce/requirements-dev.txt
          pip install -r services/identity/requirements-dev.txt
          pip install -r services/dietary/requirements-dev.txt
          pip install -r services/notification/requirements-dev.txt
          python regression/run.py --all --fail-fast --output regression/report.json
      - name: Upload report
        uses: actions/upload-artifact@v4
        with:
          name: regression-report
          path: regression/report.json
```
