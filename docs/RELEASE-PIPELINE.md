# Release Pipeline Configuration

## HRD-702: Versioned, Staged Rollout

### Versioning Strategy

#### Semantic Versioning

```
MAJOR.MINOR.PATCH
  │     │     │
  │     │     └─ Bug fixes, no API changes
  │     └─────── New features, backward-compatible API changes
  └───────────── Breaking API changes
```

#### Version Headers

All API responses include versioning headers:

```
X-API-Version: 2.1.0
X-Service-Version: 2.1.0-abc1234
X-Rollout-Stage: canary
```

### Release Pipeline Stages

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  Build   │──▶│  Staging │──▶│ Canary   │──▶│ Expanded │──▶│  Full    │
│  (100%)  │    │  (100%)  │    │ (10%)    │    │ (50%)    │    │  (100%)  │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
                    │                                    │
                    ▼                                    ▼
              Smoke Tests                          Health Checks
              Integration                          SLO Validation
              Contract                             Error Budget
```

### Stage Gates

| Gate | Criteria | Duration | Auto-Advance |
|------|----------|----------|--------------|
| Build | All CI checks pass | - | Yes |
| Staging | Smoke tests pass, contract tests pass | 15 min | Yes |
| Canary | Error rate < 0.5%, p99 < 2s, no crash reports | 30 min | Manual |
| Expanded | Error rate < 0.2%, p99 < 1.5s, SLO green | 1 hr | Manual |
| Full | All metrics green, no rollback triggered | - | Manual |

### Rollback Criteria

| Metric | Threshold | Action |
|--------|-----------|--------|
| Error rate | > 1% for 5 min | Auto-rollback |
| p99 latency | > 2s for 5 min | Auto-rollback |
| Crash rate | > 0.1% for 10 min | Auto-rollback |
| SLO burn rate | > 10x for 15 min | Auto-rollback |
| Payment failures | > 2% for 5 min | Auto-rollback |

### Deployment Configuration

```yaml
# config/deployments/staged-rollout.yaml
rollout:
  strategy: canary
  canary:
    weight: 10
    duration: 30m
    analysis:
      interval: 1m
      thresholds:
        error_rate: 0.005
        p99_latency_ms: 2000
        crash_rate: 0.001

  expanded:
    weight: 50
    duration: 60m
    analysis:
      interval: 1m
      thresholds:
        error_rate: 0.002
        p99_latency_ms: 1500
        crash_rate: 0.0005

  full:
    weight: 100

  rollback:
    auto: true
    conditions:
      - metric: error_rate
        threshold: 0.01
        duration: 5m
      - metric: p99_latency_ms
        threshold: 2000
        duration: 5m
      - metric: crash_rate
        threshold: 0.001
        duration: 10m

  traffic:
    split:
      - version: current
        weight: 100
      - version: canary
        weight: 0
```

### Release Checklist

| Step | Action | Owner | Gate |
|------|--------|-------|------|
| 1 | Merge to `release/vX.Y.Z` | Eng | PR approved |
| 2 | Build passes (all services) | CI | - |
| 3 | Deploy to staging | CI | - |
| 4 | Smoke tests pass | CI | - |
| 5 | Contract tests pass | CI | - |
| 6 | Security scan passes | CI | - |
| 7 | Canary deploy (10%) | Eng | Manual |
| 8 | Monitor 30 min | Eng | SLO green |
| 9 | Expanded deploy (50%) | Eng | Manual |
| 10 | Monitor 60 min | Eng | SLO green |
| 11 | Full deploy (100%) | Eng | Manual |
| 12 | Verify production | Eng | All green |
| 13 | Notify stakeholders | Product | - |

### Rollback Procedure

```bash
# Rollback to previous version
kubectl rollout undo deployment/ai-service -n production
kubectl rollout undo deployment/commerce-service -n production
kubectl rollout undo deployment/identity-service -n production
kubectl rollout undo deployment/dietary-service -n production
kubectl rollout undo deployment/notification-service -n production

# Verify rollback
kubectl rollout status deployment/ai-service -n production --timeout=120s
```

### Canary Analysis

```yaml
# config/canary/analysis.yaml
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata:
  name: release-analysis
spec:
  metrics:
    - name: error-rate
      provider:
        prometheus:
          address: http://prometheus:9090
          query: |
            sum(rate(http_requests_total{service=~"ai|commerce|identity|dietary|notification", status=~"5.."}[5m]))
              /
            sum(rate(http_requests_total{service=~"ai|commerce|identity|dietary|notification"}[5m]))
      successLimit: 0
      failureLimit: 3

    - name: p99-latency
      provider:
        prometheus:
          address: http://prometheus:9090
          query: |
            histogram_quantile(0.99,
              sum(rate(http_request_duration_bucket[5m])) by (le, service))
      successLimit: 0
      failureLimit: 3
```
