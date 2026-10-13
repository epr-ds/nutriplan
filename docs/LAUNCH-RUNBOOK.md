# NutriPlan GA Launch Runbook

## Purpose

Operational runbook for executing the General Availability (GA) launch of NutriPlan.
Covers pre-launch checks, launch day procedures, and post-launch monitoring.

## Prerequisites

- [ ] All GA exit criteria met (see [GA-EXIT-CRITERIA.md](GA-EXIT-CRITERIA.md))
- [ ] HRD-801: GA go-live checklist completed
- [ ] HRD-802: Production cutover verified
- [ ] HRD-706: Staged rollout + kill-switch configured
- [ ] HRD-705: App Store + Play submission approved
- [ ] HRD-804: Legal sign-off obtained
- [ ] HRD-803: Support readiness verified

## Pre-Launch Checklist (T-7 days)

### Infrastructure
- [ ] All SLOs green (API p99 < 500ms, availability > 99.9%)
- [ ] Crash-free rate > 99.5% on staging
- [ ] Monitoring dashboards configured and verified
- [ ] Alerting rules active with on-call rotation
- [ ] Runbooks for incident response reviewed

### Security
- [ ] Pentest remediation verified (HRD-106)
- [ ] PCI scope review complete (HRD-105)
- [ ] All known vulnerabilities have mitigations

### Product
- [ ] All P0/P1 features implemented and tested
- [ ] Bug bash completed, all blockers burned down (HRD-905)
- [ ] Regression suite passing (HRD-906)

### App Stores
- [ ] App Store privacy nutrition labels submitted (HRD-703)
- [ ] Play Data Safety form submitted (HRD-703)
- [ ] Store listings approved (HRD-704)
- [ ] Creative assets ready (HRD-1003)

## Launch Day Procedure

### Phase 1: Final Verification (T-2 hours)
1. Verify all CI gates green on `release/**` branch
2. Confirm staging environment matches production config
3. Verify DNS/CDN records point to production
4. Confirm on-call engineer is available

### Phase 2: Production Cutover (T-0)
1. **Enable production traffic**
   - Verify DNS TTL is low (< 300s)
   - Switch DNS to production if using canary
   - Verify CDN cache warming complete

2. **Smoke tests**
   - Run synthetic monitoring (HRD-903)
   - Verify key user journeys: signup, meal plan, deep links
   - Confirm crash-free rate > 99.5%

3. **App Store submission**
   - Submit to App Store and Play Store (if not already approved)
   - Track review status

### Phase 3: Monitoring (T+0 to T+24h)
1. **Watch dashboards**
   - API latency (p50, p95, p99)
   - Error rate and crash rate
   - Active users and session metrics
   - Payment success rate

2. **Support readiness**
   - Verify help center is live
   - Confirm support routing is active
   - Monitor social media and app store reviews

### Phase 4: Staged Rollout (T+24h to T+72h)
1. **Canary release** (10% of users)
   - Monitor for 24 hours
   - Check crash rate, error rate, performance

2. **Expand rollout** (50% of users)
   - Monitor for 12 hours
   - Check for any regressions

3. **Full rollout** (100% of users)
   - Monitor for 24 hours
   - Confirm all SLOs met

## Rollback Procedure

### Trigger Conditions
- Crash-free rate drops below 99%
- API error rate exceeds 1%
- Critical security vulnerability discovered
- Payment processing failures

### Rollback Steps
1. **Kill-switch activation** (HRD-706)
   - Disable feature flags for affected features
   - Redirect traffic to stable version

2. **App Store rollback**
   - Request App Store/Play Store to pull the app
   - Prepare hotfix if needed

3. **Post-rollback**
   - Investigate root cause
   - Fix and re-test
   - Re-submit with fix

## Post-Launch (T+1 week)

- [ ] All SLOs consistently met
- [ ] Bug bash items fully burned down
- [ ] GA sign-off obtained (HRD-805)
- [ ] Launch retrospective scheduled
- [ ] Lessons learned documented

## Contacts

| Role | Name | Contact |
|------|------|---------|
| Engineering Lead | | |
| Product Owner | | |
| Security Lead | | |
| Support Lead | | |

## References

- [GA Exit Criteria](GA-EXIT-CRITERIA.md)
- [HRD-801: GA go-live checklist](https://github.com/epr-ds/nutriplan/issues/331)
- [HRD-802: Production cutover](https://github.com/epr-ds/nutriplan/issues/344)
- [HRD-706: Staged rollout](https://github.com/epr-ds/nutriplan/issues/343)
- [HRD-903: Synthetic monitoring](https://github.com/epr-ds/nutriplan/issues/349)
