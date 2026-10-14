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

---

## HRD-602: Crash/ANR Monitoring (Crashlytics/Sentry) + Dashboards

### Architecture

```
┌───────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Android App   │────▶│ Firebase         │────▶│  Firebase       │
│  (Crashlytics) │     │ SDK/Agent        │     │  Console        │
└───────────────┘     └──────────────────┘     └────────┬────────┘
                                                         │
┌───────────────┐     ┌──────────────────┐     ┌────────▼────────┐
│  iOS App       │────▶│ Firebase         │────▶│  Crash Reports  │
│  (Crashlytics) │     │ SDK/Agent        │     │  + Symbolication│
└───────────────┘     └──────────────────┘     └─────────────────┘

┌──────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  CI (GitHub      │────▶│ Firebase          │────▶│  Symbol Storage  │
│   Actions)       │     │ Symbol Generator │     │  (GCS/Console)   │
└──────────────────┘     └──────────────────┘     └─────────────────┘
```

### Android Setup

#### Dependencies (`mobile/androidApp/build.gradle.kts`)
- Firebase BoM 33.14.0 + `firebase-crashlytics-ktx`
- Crashlytics Gradle plugin (v3.0.5) — auto-generates native symbol files

#### Initialization (`NutriPlanApplication.onCreate()`)
```kotlin
FirebaseCrashlytics.getInstance().setCrashLoggingEnabled(true)
```

#### ANR Detection
- Firebase Crashlytics auto-detects ANRs (default threshold: 5s for main thread)
- Custom ANR tracking via `FirebaseCrashlytics.getInstance().log("ANR detected in $thread")`

### iOS Setup

#### dSYM Upload in CI
- GitHub Actions job (`ios-symbols`) builds iOS framework with debug symbols
- Uses `firebase/firebase-github-actions@release/crashlytics-symbol-generator` action
- Requires `FIREBASE_SERVICE_ACCOUNT` secret (JSON service account key)

#### Crashlytics SDK Integration
- Add Firebase pod to iOS app: `pod 'Firebase/Crashlytics'`
- Initialize in `AppDelegate`: `FirebaseApp.configure()`

### Symbolication Pipeline

| Step | Tool | Output |
|------|------|--------|
| Android native symbols | Gradle Crashlytics plugin | `.so` symbol files → Firebase |
| iOS dSYM | Xcode build + Firebase action | `.dSYM` bundle → Firebase |
| Symbol resolution | Firebase backend | Human-readable stack traces |

### Crash-Free Dashboard

#### Firebase Console Views
- **Crash-free users**: Overall + per-version breakdown
- **ANR-free users**: ANR rate by version/device/OS
- **Top crashes**: Most frequent crashlytics issues with stack traces
- **Trends**: 7-day rolling crash-free percentage

#### Custom Metrics (via Firebase Custom Data)
| Metric | Source | Query |
|--------|--------|-------|
| Crash-free rate | Crashlytics SDK | `crash_free_rate >= 99.5%` |
| ANR rate | Crashlytics SDK | `anr_rate <= 0.1%` |
| App startup crashes | Custom log event | `startup_crash_count > 0` |
| Network error rate (mobile) | Ktor interceptor logs | `mobile_network_error_rate` |

### Alerting Configuration

#### Firebase Alerts (via Cloud Notifications/Slack)
| Condition | Severity | Notification |
|-----------|----------|--------------|
| Crash-free rate drops below 99% | 🔴 Critical | Slack #crash-alerts + PagerDuty |
| ANR rate exceeds 0.5% | 🟠 High | Slack #crash-alerts |
| New crash class detected (≥3 users) | 🟡 Medium | Slack #mobile-reports |
| Crash spike (>2x baseline in 1h) | 🔴 Critical | PagerDuty on-call |

#### GitHub Actions Integration
- CI job `crashlytics-android` uploads Android symbols automatically on release builds
- CI job `ios-symbols` uploads iOS dSYM files automatically on release builds
- Both jobs run only on `workflow_dispatch` or `refs/heads/release/*` branches

### Setup Checklist

- [x] Firebase Crashlytics SDK added to Android app
- [x] Crashlytics initialized in `NutriPlanApplication.onCreate()`
- [x] Crashlytics Gradle plugin configured (auto symbol generation)
- [x] CI workflow: Android symbol upload step added
- [x] CI workflow: iOS dSYM upload step added
- [ ] Firebase project created and `google-services.json` added to Android app
- [ ] Firebase service account key stored in GitHub Secrets (`FIREBASE_SERVICE_ACCOUNT`)
- [ ] iOS app configured with Crashlytics pod + initialization
- [ ] Firebase console alerts configured (Slack/PagerDuty integration)
- [ ] Crash-free dashboard reviewed and thresholds set

### Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| No crash reports in console | SDK not initialized / logging disabled | Verify `setCrashLoggingEnabled(true)` runs before first crash |
| Unsymbolicated stacks | dSYM not uploaded | Check CI logs for symbol upload step |
| Missing native frames | ProGuard mapping mismatch | Ensure Crashlytics Gradle plugin runs after minify |

---

## HRD-606: Beta Analytics + Funnel/Retention Instrumentation

### Architecture

```
┌───────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Android App   │────▶│ Firebase         │────▶│  Firebase       │
│  (Analytics)   │     │ SDK              │     │  Console        │
└───────────────┘     └──────────────────┘     └────────┬────────┘
                                                         │
┌───────────────┐     ┌──────────────────┐     ┌────────▼────────┐
│  iOS App       │────▶│ Firebase         │────▶│  Dashboards:    │
│  (Analytics)   │     │ SDK              │     │  Activation,    │
└───────────────┘     └──────────────────┘     │  D1/D7 Retention│
                                                 └─────────────────┘
```

### Android Setup

#### Dependencies (`mobile/androidApp/build.gradle.kts`)
- Firebase BoM 33.14.0 + `firebase-analytics-ktx`

#### Interface (`shared/src/commonMain/kotlin/.../analytics/AnalyticsTracker.kt`)
- Platform-agnostic `AnalyticsTracker` interface for KMP
- Consent-gated: all events skipped when `isConsentGiven == false`

#### Implementation (`androidApp/.../analytics/FirebaseAnalyticsTracker.kt`)
- Wraps `FirebaseAnalytics.getInstance(context)`
- `initialize()` — sets consent defaults
- `logScreenView()` — logs `screen_name` + `screen_class` params
- `logEvent()` — custom event with string params
- `setUserProperty()` — user properties (auth status, activation)
- `setConsent()` — enables/disables all tracking

#### Wiring
- `NutriPlanApplication` creates and exposes `FirebaseAnalyticsTracker`
- `MainActivity` passes tracker to `AppNavigationGraph`
- `AppNavigationGraph` logs screen views + funnel events per route

### Key Events Instrumented

| Event | When Logged | Params |
|-------|-------------|--------|
| `screen_view` | Every route entry | `screen_name`, `screen_class` |
| `onboarding_complete` | User taps "Get Started" | — |
| `login_success` | User signs in | — |
| `auth_status` (property) | After login | `"authenticated"` |
| `meal_plan_created` | User saves a meal plan | `plan_id` |
| `checkout_complete` | User completes checkout | — |
| `activated` (property) | After checkout | `"true"` |

### Activation + Retention Tracking

| Metric | How Tracked | Dashboard |
|--------|-------------|-----------|
| **Activation** | `activated` user property set on checkout_complete | Firebase Console → User Properties |
| **D1 Retention** | Firebase auto-tracks `first_open` + `last_active`; compare against `activated` cohort | Firebase → Retention → Day 1 |
| **D7 Retention** | Same as D1; compare against `activated` cohort | Firebase → Retention → Day 7 |
| **Funnel** | Screen view counts per route → onboarding → auth → main → meal_plan → checkout | Firebase → Funnels |

### Privacy / Consent

- All analytics events are **opt-in** by default (`consentGiven = false`)
- `AnalyticsTracker.isConsentGiven` gates every `logEvent` / `setUserProperty` call
- In production, integrate with a Consent Management Platform (CMP) to read user consent preferences
- Compliant with MX LFPDPPP: no data collected until explicit consent

### Dashboard Definitions

#### Beta Funnel Dashboard (Firebase Console)

| Funnel Step | Event | Expected Drop-off |
|-------------|-------|-------------------|
| App open | `screen_view` (splash) | — |
| Onboarding started | `screen_view` (onboarding) | ~10% |
| Onboarding completed | `onboarding_complete` | ~30% |
| Auth started | `screen_view` (auth) | ~5% |
| Auth completed | `login_success` | ~20% |
| Main screen viewed | `screen_view` (main) | ~5% |
| Meal plan created | `meal_plan_created` | ~40% |
| Checkout started | `screen_view` (checkout) | ~30% |
| Checkout completed | `checkout_complete` | ~20% |

#### Retention Cohort Dashboard

| Cohort | Metric | Target |
|--------|--------|--------|
| Activated users (checkout) | D1 retention | ≥ 40% |
| Activated users (checkout) | D7 retention | ≥ 25% |
| Onboarding completers | Activation rate | ≥ 15% |
| Login completers | Meal plan creation rate | ≥ 30% |

### Setup Checklist

- [x] Firebase Analytics dependency added to Android app
- [x] `AnalyticsTracker` interface in shared module (KMP)
- [x] `FirebaseAnalyticsTracker` implementation for Android
- [x] Tracker wired into `NutriPlanApplication` + `MainActivity`
- [x] Screen views logged for all routes
- [x] Funnel events: onboarding, login, meal plan creation, checkout
- [x] Activation property (`activated`) set on checkout
- [x] Consent-gated (opt-in by default)
- [ ] Firebase project configured with `google-services.json`
- [ ] iOS analytics implementation (FirebaseAnalytics pod)
- [ ] Firebase console funnels + retention dashboards configured
- [ ] CMP integration for production consent management
