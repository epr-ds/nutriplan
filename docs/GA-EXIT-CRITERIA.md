# GA Exit Criteria

## Purpose

Define the exit criteria for General Availability (GA) release of NutriPlan.

## Exit Criteria

### Code Quality
- [ ] All CI gates green on `release/**` branch (Backend CI, Mobile CI, Contracts, Security, Safety Regression)
- [ ] No open critical/high severity bugs
- [ ] Flakiness rate < 1 % across all test suites

### Security
- [ ] No open high/critical gitleaks findings
- [ ] Security review completed and signed off
- [ ] All known vulnerabilities have mitigations

### Performance / SLOs
- [ ] API p99 latency < 500 ms
- [ ] API availability > 99.9 %
- [ ] Mobile app crash-free rate > 99.5 %
- [ ] Dashboards configured and green

### Product
- [ ] All P0/P1 features implemented and tested
- [ ] Bug bash completed; all blockers burned down
- [ ] Product sign-off obtained

### Operations
- [ ] Runbooks for incident response
- [ ] Monitoring and alerting configured
- [ ] Rollback procedure documented and tested

## Sign-off

| Role | Name | Date | Status |
|------|------|------|--------|
| Engineering | | | |
| Product | | | |
| Security | | | |
