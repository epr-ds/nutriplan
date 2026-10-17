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

Implemented by **IDN-804** (`app/core/telemetry.py`): every request emits one structured JSON log
line carrying `request_id`/`trace_id`/`span_id`, and Prometheus metrics are exposed at `GET /metrics`.
An inbound W3C `traceparent` header is adopted so Identity spans join the caller's trace.

| Component | Metrics | Traces | Logs |
|-----------|---------|--------|------|
| HTTP | `identity_http_requests_total{method,route,status}`, `identity_http_request_duration_seconds{method,route}` | ✅ | ✅ |
| Auth | `identity_auth_events_total{event}` — `login`/`refresh`/`register`/`oauth` × `success`/`failure` | ✅ | ✅ |
| Auth errors | `identity_auth_errors_total{status}` (401/403), `identity_rate_limited_total` (429) | ✅ | ✅ |

##### Identity dashboard (login success/fail, refresh rate, p95 latency)

| Panel | Query |
|-------|-------|
| Login success rate | `sum(rate(identity_auth_events_total{event="login_success"}[5m])) / sum(rate(identity_auth_events_total{event=~"login_.*"}[5m]))` |
| Login failures / min | `sum(rate(identity_auth_events_total{event="login_failure"}[5m])) * 60` |
| Refresh rate | `sum(rate(identity_auth_events_total{event=~"refresh_.*"}[5m])) * 60` |
| p95 latency | `histogram_quantile(0.95, sum(rate(identity_http_request_duration_seconds_bucket[5m])) by (le))` |
| Rate-limit rejections / min | `sum(rate(identity_rate_limited_total[5m])) * 60` |

The `auth_failure_rate` alert is wired to `identity_auth_events_total` — see
[ALERTING.md](ALERTING.md#identity-auth_failure_rate).

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

---

## HRD-305: Accessibility Regression Checks in CI/E2E

### Automated Checks

#### Compose UI Accessibility Checks
- **Location**: `mobile/androidApp/src/androidTest/kotlin/com/nutriplan/android/a11y/AccessibilityChecksTest.kt`
- **Run**: `./gradlew :androidApp:lintDebug`
- **CI Job**: `android-a11y` in `.github/workflows/mobile.yml`
- **Critical checks**:
  1. Missing content description on interactive elements
  2. Touch target < 48x48dp (WCAG 2.5.5)
  3. Unreachable semantics node (orphaned element)
  4. Empty text without alternative

#### Detekt A11y Rules
- **Location**: `mobile/config/detekt/detekt.yml`
- **Run**: `./gradlew detekt`
- **CI Job**: `android` in `.github/workflows/mobile.yml`

### Manual Testing Checklist

- **Location**: `docs/ACCESSIBILITY-CHECKLIST.md`
- **Covers**:
  - TalkBack (screen reader) testing on all screens
  - Large font / dynamic type testing
  - Color contrast verification (WCAG AA)
  - Touch target size verification
  - Keyboard navigation testing
  - Gesture navigation testing

### CI Integration

```yaml
android-a11y:
  name: Android accessibility checks
  runs-on: ubuntu-latest
  defaults:
    run:
      working-directory: mobile
  steps:
    - uses: actions/checkout@v7
    - uses: actions/setup-java@v6
      with:
        distribution: temurin
        java-version: '17'
    - uses: gradle/actions/setup-gradle@v6
    - name: Run Compose UI a11y checks
      run: ./gradlew :androidApp:lintDebug --stacktrace
```

### Setup Checklist

- [x] Compose UI test dependency added to `androidApp/build.gradle.kts`
- [x] `AccessibilityChecksTest.kt` created with critical a11y check definitions
- [x] `android-a11y` CI job added to `.github/workflows/mobile.yml`
- [x] `docs/ACCESSIBILITY-CHECKLIST.md` created with manual testing steps
- [x] OBSERVABILITY.md updated with HRD-305 documentation
- [ ] Lint a11y rules tuned (reduce false positives)
- [ ] Compose UI tests added for each screen (requires Koin test module)

---

## HRD-1003: Store Creative — Screenshots, Preview Video, Feature Graphic

### Specification Document

- **Location**: `docs/STORE-CREATIVE-SPEC.md`
- **Covers**:
  - Google Play screenshot specs (phone, tablet, foldable, desktop)
  - App Store screenshot specs (iPhone, iPad)
  - Screenshot content plan (5 phone + 2 tablet per language)
  - Preview video specs (30s, 1920×1080, 16:9)
  - Feature graphic specs (1024×500, safe area 830×500)
  - App icon specs (512×512, solid background)
  - Store listing copy (short + full description, en/es)
  - Pre-submission validation checklist

### CI Validation Script

- **Location**: `scripts/validate-store-creative.py`
- **Validates**:
  - Screenshot dimensions against store specs (±5% tolerance)
  - Feature graphic resolution and safe area
  - App icon resolution and transparency
- **Usage**: `python scripts/validate-store-creative.py --assets-dir store-creative/ --store google_play`

### Asset Directory Structure (expected)

```
store-creative/
├── screenshots/
│   ├── en/
│   │   ├── phone/
│   │   │   ├── screenshot-1.png  (1600×3200)
│   │   │   ├── screenshot-2.png
│   │   │   ├── screenshot-3.png
│   │   │   ├── screenshot-4.png
│   │   │   └── screenshot-5.png
│   │   └── tablet/
│   │       ├── screenshot-1.png  (1920×1200)
│   │       └── screenshot-2.png
│   └── es/
│       └── ... (same structure)
├── preview-video.mp4  (1920×1080, ≤30s)
├── feature-graphic.png  (1024×500)
└── icon.png  (512×512, solid background)
```

### Setup Checklist

- [x] `docs/STORE-CREATIVE-SPEC.md` created with store specs and content plan
- [x] `scripts/validate-store-creative.py` created for CI validation
- [ ] Screenshots designed and captured (en + es)
- [ ] Preview video produced
- [ ] Feature graphic designed
- [ ] App icon finalized
- [ ] Store listing copy written (en + es)
- [ ] Legal review of store listing copy
- [ ] Design review of store creative
- [ ] Assets validated with `validate-store-creative.py`
- [ ] Assets submitted to Google Play Console
- [ ] Assets submitted to App Store Connect
