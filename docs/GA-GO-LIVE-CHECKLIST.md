# GA Go-Live Checklist (HRD-801)

## Purpose

Systematic checklist to verify all prerequisites before NutriPlan goes live.
Each item must be checked off by the responsible role before GA sign-off.

## Pre-Launch Readiness

### Engineering (HRD-805)
- [ ] All CI gates green on `release/**` branch
- [ ] Regression suite passing (HRD-906)
- [ ] API p99 latency < 500ms
- [ ] API availability > 99.9%
- [ ] Mobile crash-free rate > 99.5%
- [ ] SLOs configured with dashboards (HRD-501)
- [ ] Alerting + on-call rotation active (HRD-502)
- [ ] Production observability complete (HRD-506)

### Security & Compliance (HRD-104/105/106)
- [ ] Pentest remediation verified (HRD-106)
- [ ] PCI scope review complete (HRD-105)
- [ ] Account deletion + data export working (HRD-104)
- [ ] Security review signed off

### Product (HRD-905)
- [ ] All P0/P1 features implemented
- [ ] Bug bash completed
- [ ] All blockers burned down
- [ ] Product sign-off obtained

### App Store Readiness (HRD-702/703/704/705)
- [ ] Release pipelines configured (HRD-702)
- [ ] Play Data Safety submitted (HRD-703)
- [ ] App Store privacy nutrition labels submitted (HRD-703)
- [ ] Store listings approved (HRD-704)
- [ ] App Store + Play submission approved (HRD-705)
- [ ] Store creative assets ready (HRD-1003)

### Operations (HRD-802/801)
- [ ] Production cutover verified (HRD-802)
- [ ] DNS/CDN configured
- [ ] Staged rollout configured (HRD-706)
- [ ] Kill-switch tested
- [ ] Launch runbook reviewed
- [ ] Runbooks + incident response playbooks (HRD-503)
- [ ] Backup/restore drill completed (HRD-504)

### Support (HRD-803)
- [ ] Help center live
- [ ] FAQ published
- [ ] Support routing configured

### Accessibility (HRD-301/302/303/304/305)
- [ ] WCAG 2.1 AA audit complete (HRD-301)
- [ ] Accessibility fixes applied (HRD-302/303)
- [ ] Dynamic type / contrast pass complete (HRD-304)
- [ ] Accessibility regression checks in CI (HRD-305)

### Localization (HRD-401/402/403/404)
- [ ] Localization audit complete (HRD-401)
- [ ] MXN currency, dates, numbers formatted (HRD-402)
- [ ] Store metadata localized (HRD-403)
- [ ] In-app legal content localized (HRD-404)

## Sign-Off

| Role | Name | Date | Status |
|------|------|------|--------|
| Engineering | | | |
| Product | | | |
| Security | | | |
| Operations | | | |
| Support | | | |

## Go/No-Go Decision

**Date**: __________
**Decision**: [ ] GO / [ ] NO-GO
**Rationale**: _________________________________________________

**Approved by**: _______________________________________________
