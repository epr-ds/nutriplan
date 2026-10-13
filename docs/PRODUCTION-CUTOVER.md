# Production Cutover Plan (HRD-802)

## Purpose

Step-by-step plan for cutover from staging to production, including DNS/CDN configuration, scaling validation, and rollback procedures.

## Pre-Cutover Requirements

- [ ] Staging environment mirrors production config
- [ ] Load testing completed to target RPS (HRD-202)
- [ ] Autoscaling rules validated (HRD-206)
- [ ] DNS records prepared with low TTL
- [ ] CDN cache warming strategy defined
- [ ] Database migration scripts tested on staging

## Cutover Procedure

### Step 1: DNS Configuration
1. Verify current DNS records
2. Set TTL to 60s for all production domains
3. Prepare A/AAAA records pointing to production load balancer
4. Verify DNS propagation tools ready

### Step 2: CDN Configuration
1. Configure CDN origin to production backend
2. Set cache rules for static assets
3. Prepare cache invalidation script
4. Verify SSL/TLS certificates valid

### Step 3: Scaling Validation
1. Verify autoscaling rules:
   - CPU threshold: < 70%
   - Memory threshold: < 80%
   - Request count per instance: < 1000 RPS
2. Configure minimum instances: 3
3. Configure maximum instances: 20
4. Test scale-up trigger

### Step 4: Database Cutover
1. Verify database replication lag < 1s
2. Run migration scripts on staging (dry run)
3. Schedule migration window
4. Prepare rollback migration scripts

### Step 5: Traffic Switch
1. **Canary (10%)**
   - Update DNS to point 10% to production
   - Monitor for 30 minutes
   - Check error rate, latency, crash rate

2. **Expand (50%)**
   - Update DNS to point 50% to production
   - Monitor for 30 minutes
   - Check all SLOs

3. **Full (100%)**
   - Update DNS to point 100% to production
   - Monitor for 2 hours
   - Confirm all systems healthy

### Step 6: Post-Cutover Verification
1. Run synthetic monitoring (HRD-903)
2. Verify all API endpoints responding
3. Confirm mobile app can connect
4. Verify payment processing
5. Check monitoring dashboards green

## Rollback Procedure

### Trigger Conditions
- Error rate > 1% for > 5 minutes
- API p99 latency > 2s for > 5 minutes
- Crash rate > 1%
- Database connection failures

### Rollback Steps
1. **Immediate**: Revert DNS to staging
2. **Notify**: Alert on-call engineer and product team
3. **Investigate**: Check logs, metrics, traces
4. **Fix**: Address root cause
5. **Re-test**: Verify fix on staging
6. **Retry**: Attempt cutover again

## Contact List

| Role | Name | Phone | Email |
|------|------|-------|-------|
| On-call Engineer | | | |
| DBA | | | |
| Network Engineer | | | |
| Product Owner | | | |

## References

- [HRD-801: GA go-live checklist](GA-GO-LIVE-CHECKLIST.md)
- [HRD-706: Staged rollout](https://github.com/epr-ds/nutriplan/issues/343)
- [HRD-903: Synthetic monitoring](https://github.com/epr-ds/nutriplan/issues/349)
- [HRD-202: Load testing](https://github.com/epr-ds/nutriplan/issues/304)
- [HRD-206: Autoscaling](https://github.com/epr-ds/nutriplan/issues/318)
