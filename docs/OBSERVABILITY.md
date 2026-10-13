# Production Observability

## HRD-506: Traces, Logs, Metrics Completeness

### Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Services   │────▶│  OpenTelemetry│────▶│  Grafana    │
│  (Python)   │     │  (SDK/Agent)  │     │  (UI)       │
└─────────────┘     └──────────────┘     └──────┬──────┘
                                                  │
┌─────────────┐     ┌──────────────┐     ┌──────▼──────┐
│  Mobile     │────▶│  SDK/Agent   │────▶│  Loki       │
│  (KMP)      │     │  (Crashlytics)│     │  (Logs)     │
└─────────────┘     └──────────────┘     └─────────────┘
                                                  │
┌─────────────┐     ┌──────────────┐     ┌──────▼──────┐
│  K6 Tests   │────▶│  Metrics     │────▶│  Prometheus │
│  (Load/Syn) │     │  Export      │     │  (Metrics)  │
└─────────────┘     └──────────────┘     └─────────────┘
```

### Service Instrumentation Checklist

#### AI Service (`services/ai/`)

| Component | Metrics | Traces | Logs |
|-----------|---------|--------|------|
| LLM provider | `llm_request_duration`, `llm_token_count`, `llm_failure_count` | ✅ | ✅ |
| Cache | `cache_hit_rate`, `cache_eviction_rate` | ✅ | ✅ |
| KV store | `kv_operation_duration`, `kv_error_rate` | ✅ | ✅ |
| Optimization | `optimization_duration`, `optimization_quality_score` | ✅ | ✅ |
| Guardrails | `guardrails_violation_count`, `guardrails_sanitization_rate` | ✅ | ✅ |
| Recommendations | `recommendation_diversity_score`, `recommendation_latency` | ✅ | ✅ |

#### Commerce Service (`services/commerce/`)

| Component | Metrics | Traces | Logs |
|-----------|---------|--------|------|
| Order creation | `order_creation_duration`, `order_success_rate` | ✅ | ✅ |
| Payment | `payment_processing_duration`, `payment_failure_rate` | ✅ | ✅ |
| Grocery | `grocery_adapter_latency`, `grocery_failure_rate` | ✅ | ✅ |
| Slot reservation | `slot_reservation_duration`, `slot_availability` | ✅ | ✅ |
| Webhooks | `webhook_processing_duration`, `webhook_retry_count` | ✅ | ✅ |

#### Identity Service (`services/identity/`)

| Component | Metrics | Traces | Logs |
|-----------|---------|--------|------|
| Auth | `auth_success_rate`, `auth_latency`, `auth_rate_limit_count` | ✅ | ✅ |
| JWT | `jwt_validation_duration`, `jwt_failure_count` | ✅ | ✅ |
| OAuth | `oauth_callback_duration`, `oauth_failure_rate` | ✅ | ✅ |
| Profile | `profile_update_duration`, `profile_cache_hit_rate` | ✅ | ✅ |

#### Dietary Service (`services/dietary/`)

| Component | Metrics | Traces | Logs |
|-----------|---------|--------|------|
| Meal plans | `meal_plan_duration`, `meal_plan_cache_hit_rate` | ✅ | ✅ |
| Recipes | `recipe_search_duration`, `recipe_result_count` | ✅ | ✅ |
| MongoDB | `mongo_query_duration`, `mongo_connection_pool` | ✅ | ✅ |

#### Notification Service (`services/notification/`)

| Component | Metrics | Traces | Logs |
|-----------|---------|--------|------|
| Push (FCM/APNS) | `push_delivery_duration`, `push_failure_rate` | ✅ | ✅ |
| Dead letter queue | `dlq_message_count`, `dlq_replay_duration` | ✅ | ✅ |
| Preferences | `preference_update_duration`, `preference_cache_hit_rate` | ✅ | ✅ |

### OpenTelemetry Configuration

```yaml
# config/otel/config.yaml
service:
  telemetry:
    logs:
      level: info
      encoding: json
    metrics:
      level: detailed
    traces:
      sampler: parent_based_remote(0.1)  # 10% sampling for prod
      propagators: [tracecontext, baggage]

exporters:
  otlp:
    endpoint: otel-collector:4317
    tls:
      insecure: false
  prometheus:
    endpoint: 0.0.0.0:8889
  loki:
    endpoint: http://loki:3100/loki/api/v1/push

resource_detectors:
  - service.name: ${OTEL_SERVICE_NAME}
  - service.version: ${OTEL_SERVICE_VERSION}
  - host
  - os
```

### Dashboard Definitions

#### Service Health Dashboard

| Panel | Type | Query |
|-------|------|-------|
| Request Rate | Graph | `rate(http_requests_total[5m])` |
| Error Rate | Graph | `rate(http_requests_total{status=~"5.."}[5m])` |
| Latency p50/p95/p99 | Graph | `histogram_quantile(0.95, rate(http_request_duration_bucket[5m]))` |
| Active Connections | Gauge | `active_connections` |
| CPU/Memory | Gauge | `process_cpu_usage`, `process_resident_memory_bytes` |

#### Business Metrics Dashboard

| Panel | Type | Query |
|-------|------|-------|
| Orders/hour | Graph | `rate(orders_total[1h])` |
| Payment success rate | Gauge | `payment_success_rate` |
| Active users (DAU) | Gauge | `active_users{period="d"}` |
| Meal plans created | Graph | `rate(meal_plans_created_total[1h])` |
| Recipe searches | Graph | `rate(recipe_searches_total[1h])` |

#### Mobile Health Dashboard

| Panel | Type | Query |
|-------|------|-------|
| Crash-free rate | Gauge | `crash_free_rate` |
| ANR rate | Gauge | `anr_rate` |
| App startup time | Histogram | `app_startup_duration` |
| Screen load time | Histogram | `screen_load_duration` |
| API error rate (mobile) | Graph | `rate(mobile_api_errors_total[5m])` |

### Log Standards

#### Structured Log Format

```json
{
  "timestamp": "2026-10-13T20:00:00Z",
  "level": "INFO",
  "service": "ai",
  "trace_id": "abc123",
  "span_id": "def456",
  "message": "Meal analysis completed",
  "duration_ms": 245,
  "user_id": "usr_123",
  "request_id": "req_789",
  "metadata": {
    "meal_id": "meal_456",
    "model": "claude-3-opus",
    "tokens_used": 1024
  }
}
```

#### Log Levels

| Level | When to Use | Examples |
|-------|-------------|----------|
| DEBUG | Detailed diagnostic info | Request params, cache keys |
| INFO | Normal operational events | Request completed, user logged in |
| WARN | Unexpected but handled | Retry attempt, cache miss |
| ERROR | Error but service continues | DB connection timeout, API error |
| FATAL | Service cannot continue | Config missing, disk full |

### Trace Sampling Strategy

| Environment | Sampling Rate | Notes |
|-------------|---------------|-------|
| Development | 100% | All traces |
| Staging | 50% | Most traces |
| Production | 10% | Sampled, with 100% for errors |
| Production (error) | 100% | All error traces |

### Alerting from Observability

| Metric | Alert Condition | Action |
|--------|----------------|--------|
| `up` == 0 | Target down | Page on-call |
| `rate(http_requests_total{status=~"5.."}[5m]) > 0.01` | > 1% errors | Page on-call |
| `histogram_quantile(0.99, rate(http_request_duration_bucket[5m])) > 2` | p99 > 2s | Page on-call |
| `go_goroutines > 10000` | Goroutine leak | Page on-call |
| `process_open_fds > 1000` | File descriptor leak | Page on-call |
