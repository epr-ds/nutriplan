# NutriPlan SLOs + Error Budgets (HRD-501)
# Service-level objectives and error budgets per service

## Overview

SLOs define the target reliability for each service. Error budgets track how much
reliability has been "spent" — when exhausted, releases are frozen until recovery.

---

## API Service

| Metric | Target | Measurement | Window |
|--------|--------|-------------|--------|
| Availability | 99.9% | HTTP 2xx / total requests | Rolling 30d |
| p50 Latency | < 200ms | HTTP response time | Rolling 7d |
| p95 Latency | < 500ms | HTTP response time | Rolling 7d |
| p99 Latency | < 1000ms | HTTP response time | Rolling 7d |

**Error Budget**: 8.76 hours/month (99.9% availability)
**Burn Rate Alerts**:
- Fast: > 2x budget spent in 1h → page on-call
- Slow: > 1x budget spent in 6h → notify team

---

## Mobile Backend

| Metric | Target | Measurement | Window |
|--------|--------|-------------|--------|
| Availability | 99.95% | HTTP 2xx / total requests | Rolling 30d |
| p50 Latency | < 150ms | HTTP response time | Rolling 7d |
| p95 Latency | < 300ms | HTTP response time | Rolling 7d |
| Crash-free Rate | > 99.5% | Crashlytics/Sentry | Rolling 7d |

**Error Budget**: 21.9 minutes/month (99.95% availability)
**Burn Rate Alerts**:
- Fast: > 2x budget spent in 30m → page on-call
- Slow: > 1x budget spent in 3h → notify team

---

## AI Service

| Metric | Target | Measurement | Window |
|--------|--------|-------------|--------|
| Availability | 99.5% | HTTP 2xx / total requests | Rolling 30d |
| p50 Latency | < 2000ms | HTTP response time | Rolling 7d |
| p95 Latency | < 5000ms | HTTP response time | Rolling 7d |
| Safety Pass Rate | 100% | Allergen safety check | Per request |

**Error Budget**: 3.6 hours/month (99.5% availability)
**Burn Rate Alerts**:
- Fast: > 2x budget spent in 2h → page on-call
- Slow: > 1x budget spent in 12h → notify team

---

## Database

| Metric | Target | Measurement | Window |
|--------|--------|-------------|--------|
| Availability | 99.99% | Connection success rate | Rolling 30d |
| Replication Lag | < 1s | Primary → replica | Per minute |
| Query p95 | < 50ms | Slow query log | Rolling 7d |

**Error Budget**: 4.32 minutes/month (99.99% availability)
**Burn Rate Alerts**:
- Replication lag > 5s for 1m → page on-call
- Connection failures > 0.1% → page on-call

---

## Error Budget Policy

| Budget Remaining | Action |
|------------------|--------|
| > 50% | Normal operations |
| 25-50% | Monitor closely, prepare rollback |
| 10-25% | Freeze non-critical releases |
| < 10% | Freeze all releases, focus on recovery |
| 0% | Incident declared, all hands on deck |

## Dashboard Links

| Dashboard | URL |
|-----------|-----|
| API SLOs | TBD |
| Mobile SLOs | TBD |
| AI Service SLOs | TBD |
| Database SLOs | TBD |
| Error Budget Tracker | TBD |

## References

- [HRD-501: SLOs + error budgets](https://github.com/epr-ds/nutriplan/issues/308)
- [HRD-502: Alerting + on-call](https://github.com/epr-ds/nutriplan/issues/309)
- [HRD-506: Production observability](https://github.com/epr-ds/nutriplan/issues/310)
