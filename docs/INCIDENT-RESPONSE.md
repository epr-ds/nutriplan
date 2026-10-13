# Incident Response Playbooks (HRD-503)

## Purpose

Standard operating procedures for responding to common incidents on NutriPlan.

---

## Playbook 1: High Error Rate (> 1% for > 5 min)

### Detection
- Alert: `api_error_rate > 0.01 for 5m`
- Dashboard: API SLOs

### Triage
1. Check deployment history: `git log --oneline -10`
2. Check recent config changes
3. Check database connection pool
4. Check third-party service status (payments, email, etc.)

### Response
| Symptom | Action |
|---------|--------|
| Post-deployment spike | Rollback: `kubectl rollout undo deployment/api` |
| Database connection exhaustion | Scale DB, kill idle connections |
| Third-party outage | Enable circuit breaker, queue retries |
| Traffic spike | Enable rate limiting, scale horizontally |

### Verification
- Error rate drops below 0.1%
- p95 latency < 500ms
- All synthetic monitors green

### Post-Incident
- Create follow-up issue for root cause
- Update runbook if new scenario discovered
- Schedule blameless retrospective

---

## Playbook 2: High Crash Rate (> 1% crash-free rate drop)

### Detection
- Alert: `crash_free_rate < 0.99 for 15m`
- Source: Crashlytics / Sentry

### Triage
1. Check recent app releases (App Store / Play Store)
2. Check for new crash clusters
3. Check OS version distribution
4. Check device-specific patterns

### Response
| Symptom | Action |
|---------|--------|
| New release causing crashes | Pause distribution, prepare hotfix |
| OS update causing crashes | Release emergency patch |
| Device-specific crashes | Target fix to affected devices |
| Third-party SDK crash | Update/disable SDK, release patch |

### Verification
- Crash-free rate recovers to > 99.5%
- No new crash clusters in 1h
- Hotfix approved by stores

### Post-Incident
- Add regression test for crash scenario
- Update device matrix (HRD-902)
- Update crash monitoring (HRD-602)

---

## Playbook 3: API Latency Spike (p99 > 2s)

### Detection
- Alert: `api_latency_p99 > 2000 for 5m`
- Dashboard: API SLOs

### Triage
1. Check database query performance
2. Check cache hit rates
3. Check external API response times
4. Check resource utilization (CPU, memory, disk)

### Response
| Symptom | Action |
|---------|--------|
| Slow queries | Add query hint, kill long queries |
| Cache miss storm | Warm cache, increase TTL |
| External API slow | Enable circuit breaker, use cached data |
| Resource exhaustion | Scale horizontally, kill zombie processes |

### Verification
- p99 latency < 1s
- p95 latency < 500ms
- Error rate < 0.1%

### Post-Incident
- Add performance regression test
- Update capacity plan (HRD-206)
- Optimize slow queries

---

## Playbook 4: Security Incident

### Detection
- Alert: Unusual access patterns
- Manual report via security contact

### Triage
1. Identify affected systems/users
2. Check for data exposure
3. Check for unauthorized access
4. Preserve evidence

### Response
| Symptom | Action |
|---------|--------|
| Credential leak | Rotate keys, revoke sessions |
| Unauthorized access | Block IP, disable account |
| Data exposure | Notify affected users, legal |
| DDoS | Enable WAF rules, scale infrastructure |

### Verification
- Threat contained
- No further unauthorized access
- All affected systems secured

### Post-Incident
- Security review (HRD-106)
- Update security controls
- Notify users if data exposed
- Legal compliance review (HRD-105)

---

## Escalation Matrix

| Severity | Response Time | Escalation |
|----------|--------------|------------|
| SEV-1 (Critical) | 15 min | Engineering Lead → CTO |
| SEV-2 (High) | 30 min | Engineering Lead → VP Eng |
| SEV-3 (Medium) | 2 hours | Team lead → Engineering Lead |
| SEV-4 (Low) | 24 hours | Team lead |

## Communication Templates

### Initial Alert
```
🚨 [SEV-X] Brief incident description
Started: <time>
Impact: <what users are affected>
Status: Investigating
Next update: <time + 15min>
```

### Resolution
```
✅ [SEV-X] Incident resolved
Duration: <start> to <end>
Impact: <summary>
Root cause: <brief>
Follow-up: <issue link>
```

## References

- [HRD-503: Runbooks + incident response](https://github.com/epr-ds/nutriplan/issues/323)
- [HRD-502: Alerting + on-call](https://github.com/epr-ds/nutriplan/issues/309)
- [HRD-501: SLOs + error budgets](https://github.com/epr-ds/nutriplan/issues/308)
