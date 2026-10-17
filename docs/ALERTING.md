# Alerting Configuration

## HRD-502: Alerting + On-Call Rotation

### Alert Rules

#### Error Rate Alerts

| Alert | Condition | Duration | Severity | Channel |
|-------|-----------|----------|----------|---------|
| `high_error_rate` | error_rate > 1% | 5m | P1 | PagerDuty + #incidents |
| `critical_error_rate` | error_rate > 5% | 2m | P0 | PagerDuty + #incidents + page on-call |
| `error_rate_spike` | error_rate > 2x baseline | 3m | P2 | #incidents |

#### Latency Alerts

| Alert | Condition | Duration | Severity | Channel |
|-------|-----------|----------|----------|---------|
| `high_p95_latency` | p95 > 500ms | 5m | P2 | #incidents |
| `high_p99_latency` | p99 > 1000ms | 5m | P2 | #incidents |
| `critical_latency` | p99 > 2000ms | 2m | P1 | PagerDuty + #incidents |

#### Service-Specific Alerts

| Service | Alert | Threshold | Severity |
|---------|-------|-----------|----------|
| AI | `llm_failure_rate` | > 2% | P1 |
| AI | `llm_latency_p99` | > 3000ms | P2 |
| Commerce | `payment_failure_rate` | > 1% | P0 |
| Commerce | `order_queue_depth` | > 100 | P2 |
| Identity | `auth_failure_rate` | > 5% | P1 |
| Dietary | `mongo_connection_errors` | > 0 | P1 |
| Notification | `push_delivery_failure` | > 5% | P2 |

#### Identity `auth_failure_rate` (implemented, IDN-804)

Backed by `identity_auth_events_total` from `services/identity/app/core/telemetry.py`; scrape
`GET /metrics` on the Identity service.

```promql
# Fire when >5% of auth attempts fail over 5m.
sum(rate(identity_auth_events_total{event=~"(login|refresh|oauth)_failure"}[5m]))
  / sum(rate(identity_auth_events_total[5m])) > 0.05
```

A companion signal, `identity_rate_limited_total` (429s), is also exported for throttling spikes.

#### Infrastructure Alerts

| Alert | Condition | Severity |
|-------|-----------|----------|
| `high_cpu` | CPU > 80% for 10m | P2 |
| `high_memory` | Memory > 85% for 10m | P2 |
| `disk_space_low` | Disk < 10% | P1 |
| `pod_crash_loop` | Pod restarts > 3 in 15m | P1 |
| `database_connections_high` | > 80% max connections | P2 |

### On-Call Rotation

#### Schedule

| Week | Primary | Secondary |
|------|---------|-----------|
| W1 | eng-oncall-1 | eng-oncall-2 |
| W2 | eng-oncall-2 | eng-oncall-3 |
| W3 | eng-oncall-3 | eng-oncall-1 |
| W4 | eng-oncall-1 | eng-oncall-2 |

#### Escalation Policy

| Level | Action | Delay |
|-------|--------|-------|
| L1 | Page on-call engineer | Immediate |
| L2 | Page engineering manager | 10 min if unacknowledged |
| L3 | Page VP Engineering | 25 min if unacknowledged |
| L4 | Activate incident commander | 45 min if unacknowledged |

#### Response SLAs

| Severity | Acknowledge | Triage | Resolve | Update Interval |
|----------|-------------|---------|---------|-----------------|
| P0 | 5 min | 15 min | 1 hr | Every 15 min |
| P1 | 10 min | 30 min | 4 hrs | Every 30 min |
| P2 | 30 min | 2 hrs | Next sprint | Every 2 hrs |
| P3 | 1 business day | 2 business days | Backlog | Daily |

### Alert Routing

```yaml
# config/alerting/routes.yaml
routes:
  - match:
      severity: P0
    receiver: pagerduty-critical
    continue: true

  - match:
      severity: P1
    receiver: pagerduty-high
    continue: true

  - match:
      severity: P2
    receiver: slack-incidents
    continue: true

  - match:
      severity: P3
    receiver: slack-incidents
    continue: false

receivers:
  - name: pagerduty-critical
    pagerduty:
      service_key: ${PAGERDUTY_CRITICAL_KEY}

  - name: pagerduty-high
    pagerduty:
      service_key: ${PAGERDUTY_HIGH_KEY}

  - name: slack-incidents
    slack:
      channel: '#incidents'
      token: ${SLACK_BOT_TOKEN}
```

### Runbook References

| Alert | Runbook |
|-------|---------|
| high_error_rate | INCIDENT-RESPONSE.md#high-error-rate |
| critical_error_rate | INCIDENT-RESPONSE.md#high-error-rate |
| high_p95_latency | INCIDENT-RESPONSE.md#latency-spike |
| high_p99_latency | INCIDENT-RESPONSE.md#latency-spike |
| llm_failure_rate | INCIDENT-RESPONSE.md#ai-service-failures |
| payment_failure_rate | INCIDENT-RESPONSE.md#payment-failures |
| auth_failure_rate | INCIDENT-RESPONSE.md#auth-failures |
