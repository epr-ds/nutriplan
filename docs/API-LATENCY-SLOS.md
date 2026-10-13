# API Latency SLOs Per Endpoint

## HRD-204: API Latency Budgets

### Service: AI Service

| Endpoint | Method | p50 Budget | p95 Budget | p99 Budget | Error Budget | Notes |
|----------|--------|------------|------------|------------|--------------|-------|
| `/api/v1/analysis` | POST | 200ms | 500ms | 1500ms | 0.5% | Meal analysis |
| `/api/v1/analysis/optimize` | POST | 300ms | 800ms | 2000ms | 0.5% | Meal optimization |
| `/api/v1/recommendations` | GET | 100ms | 300ms | 800ms | 0.5% | Recipe recommendations |
| `/api/v1/analysis/health` | GET | 50ms | 100ms | 200ms | 0.1% | Health check |

### Service: Identity Service

| Endpoint | Method | p50 Budget | p95 Budget | p99 Budget | Error Budget | Notes |
|----------|--------|------------|------------|------------|--------------|-------|
| `/api/v1/auth/login` | POST | 150ms | 400ms | 1000ms | 0.5% | Login |
| `/api/v1/auth/refresh` | POST | 50ms | 150ms | 400ms | 0.5% | Token refresh |
| `/api/v1/auth/logout` | POST | 30ms | 100ms | 200ms | 0.1% | Logout |
| `/api/v1/users/me` | GET | 50ms | 150ms | 400ms | 0.5% | Profile fetch |
| `/api/v1/users/me` | PUT | 100ms | 300ms | 800ms | 0.5% | Profile update |
| `/api/v1/jwks` | GET | 20ms | 50ms | 100ms | 0.1% | JWKS endpoint |

### Service: Commerce Service

| Endpoint | Method | p50 Budget | p95 Budget | p99 Budget | Error Budget | Notes |
|----------|--------|------------|------------|------------|--------------|-------|
| `/api/v1/orders` | POST | 200ms | 500ms | 1500ms | 0.1% | Create order |
| `/api/v1/orders/{id}` | GET | 50ms | 150ms | 400ms | 0.5% | Get order |
| `/api/v1/orders` | GET | 100ms | 300ms | 800ms | 0.5% | List orders |
| `/api/v1/orders/{id}/cancel` | POST | 150ms | 400ms | 1000ms | 0.1% | Cancel order |
| `/api/v1/payments` | POST | 300ms | 800ms | 2000ms | 0.1% | Process payment |
| `/api/v1/slots/reserve` | POST | 50ms | 150ms | 400ms | 0.5% | Reserve slot |
| `/api/v1/grocery/search` | GET | 100ms | 300ms | 800ms | 0.5% | Search products |

### Service: Dietary Service

| Endpoint | Method | p50 Budget | p95 Budget | p99 Budget | Error Budget | Notes |
|----------|--------|------------|------------|------------|--------------|-------|
| `/api/v1/meal-plans` | POST | 100ms | 300ms | 800ms | 0.5% | Create meal plan |
| `/api/v1/meal-plans/{id}` | GET | 30ms | 100ms | 300ms | 0.5% | Get meal plan |
| `/api/v1/meal-plans` | GET | 50ms | 150ms | 400ms | 0.5% | List meal plans |
| `/api/v1/recipes` | GET | 50ms | 150ms | 400ms | 0.5% | Search recipes |
| `/api/v1/recipes/{id}` | GET | 30ms | 100ms | 300ms | 0.5% | Get recipe |

### Service: Notification Service

| Endpoint | Method | p50 Budget | p95 Budget | p99 Budget | Error Budget | Notes |
|----------|--------|------------|------------|------------|--------------|-------|
| `/api/v1/notifications` | POST | 50ms | 150ms | 400ms | 0.5% | Send notification |
| `/api/v1/notifications/preferences` | GET | 30ms | 100ms | 300ms | 0.5% | Get preferences |
| `/api/v1/notifications/preferences` | PUT | 50ms | 150ms | 400ms | 0.5% | Update preferences |
| `/api/v1/notifications/health` | GET | 20ms | 50ms | 100ms | 0.1% | Health check |

### Latency Budget Burn Rate

| Burn Rate | p99 vs Budget | Action |
|-----------|---------------|--------|
| 1x | Within budget | Normal monitoring |
| 2x | 2x budget consumed | Alert on-call |
| 5x | 5x budget consumed | Page on-call, investigate |
| 10x | 10x budget consumed | P0 incident |

### Error Budget Calculation

```
Monthly Error Budget = 100% - SLO
Allowed Errors = Monthly Requests × Error Budget
Burn Rate = Error Consumption Rate / Allowed Error Rate

Example (AI service, 99.5% SLO):
  Monthly Error Budget = 0.5%
  If 1M requests/month → 5,000 allowed errors
  1x burn rate = 5,000 errors/month
  2x burn rate = 10,000 errors/month → alert
  10x burn rate = 50,000 errors/month → page
```

### Monitoring Queries

```promql
# Latency budget burn rate (5m window)
rate(http_request_duration_bucket{service="ai", le="+Inf"}[5m])
  /
rate(http_request_duration_bucket{service="ai", le="500"}[5m])

# Error budget burn rate (1h window)
rate(http_requests_total{service="ai", status=~"5.."}[1h])
  /
rate(http_requests_total{service="ai"}[1h])

# Per-endpoint latency
histogram_quantile(0.99,
  rate(http_request_duration_bucket{service="ai"}[5m]))
```
