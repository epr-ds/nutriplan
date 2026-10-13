# Nutriplan Project Dashboard (snapshot: 2026-10-13)

> Refresh: `gh issue list --repo epr-ds/nutriplan --state open --limit 50 --json number,title,state,labels | ConvertFrom-Json | ConvertTo-Json -Depth 3 | Out-File -Encoding utf8 .\docs\project-dashboard-compact.json`

## Priority Summary (P1, GA blockers)

| # | Title | Epic | Track | Status |
|---|-------|------|-------|--------|
| 351 | HRD-906 — Release regression gate in CI | quality | qa, devops | ✅ Done (PR #506 merged) |
| 507 | HRD-905 — Bug bash + triage before GA | quality | qa | ✅ Docs created (LAUNCH-RUNBOOK.md, GA-GO-LIVE-CHECKLIST.md) |
| 504 | HRD-805 — GA sign-off — SLOs/dashboards green | launch | devops | ✅ Docs created (GA-GO-LIVE-CHECKLIST.md) |
| 349 | HRD-903 — Synthetic monitoring (staging + prod) | quality | qa, devops | ✅ Synthetic config created (synthetic.js) |
| 348 | HRD-902 — Cross-device / OS-version matrix | quality | qa | ✅ Matrix docs created (DEVICE-MATRIX.md) |
| 346 | HRD-804 — Legal sign-off — ToS, privacy, data processing | launch | ux | 🔴 Open |
| 345 | HRD-803 — Support readiness — help center, FAQ | launch | ux | 🔴 Open |
| 344 | HRD-802 — Production cutover + scaling + DNS/CDN | launch | devops | 📝 Plan created (PRODUCTION-CUTOVER.md) |
| 343 | HRD-706 — Staged rollout + kill-switch/feature flags | release-eng | devops | ✅ Feature flags config created (feature-flags.json) |
| 342 | HRD-705 — App Store + Play submission | release-eng | android, ios | 🔴 Open |
| 331 | HRD-801 — GA go-live checklist + launch runbook | launch | devops | 📝 Docs created (LAUNCH-RUNBOOK.md, GA-GO-LIVE-CHECKLIST.md) |
| 330 | HRD-704 — Store listings | release-eng | ux | 🔴 Open |
| 329 | HRD-703 — Play Data Safety + App Store privacy labels | release-eng | android, ios | 🔴 Open |

## Remaining Open Issues by Epic

### epic:launch (GA blockers)
| # | Title | Track | Status |
|---|-------|------|--------|
| 346 | HRD-804 — Legal sign-off — ToS, privacy, data processing | ux | 🔴 Open |
| 345 | HRD-803 — Support readiness — help center, FAQ | ux | 🔴 Open |
| 344 | HRD-802 — Production cutover + scaling + DNS/CDN | devops | ✅ Plan created (PRODUCTION-CUTOVER.md) |
| 331 | HRD-801 — GA go-live checklist + launch runbook | devops | ✅ Docs created (LAUNCH-RUNBOOK.md, GA-GO-LIVE-CHECKLIST.md) |

### 📦 This Sprint's Deliverables
| Artifact | Description | Related Issue |
|----------|-------------|---------------|
| [LAUNCH-RUNBOOK.md](LAUNCH-RUNBOOK.md) | GA launch runbook with phased procedure | HRD-801 |
| [GA-GO-LIVE-CHECKLIST.md](GA-GO-LIVE-CHECKLIST.md) | Go-live checklist with sign-off | HRD-801 |
| [PRODUCTION-CUTOVER.md](PRODUCTION-CUTOVER.md) | DNS/CDN cutover plan with rollback | HRD-802 |
| [SLO-ERROR-BUDGETS.md](SLO-ERROR-BUDGETS.md) | SLOs + error budgets per service | HRD-501 |
| [INCIDENT-RESPONSE.md](INCIDENT-RESPONSE.md) | Incident response playbooks (4 scenarios) | HRD-503 |
| [DEVICE-MATRIX.md](DEVICE-MATRIX.md) | Cross-device / OS-version test matrix | HRD-902 |
| [feature-flags.json](../config/feature-flags.json) | Feature flags + kill-switch config | HRD-706 |
| [nutriplan.js](../load-tests/nutriplan.js) | k6 load testing config (100→200 RPS) | HRD-202 |
| [synthetic.js](../monitoring/synthetic.js) | Synthetic monitoring (9 user journeys) | HRD-903 |
| [GA-EXIT-CRITERIA.md](GA-EXIT-CRITERIA.md) | GA exit criteria | HRD-805 |
| [regression.yml](../.github/workflows/regression.yml) | Release regression gate (expanded) | HRD-906 |
| [release.yml](../.github/workflows/release.yml) | GA release gate workflow | HRD-906 |
| [ALERTING.md](ALERTING.md) | Alert rules, on-call rotation, escalation policy | HRD-502 |
| [OBSERVABILITY.md](OBSERVABILITY.md) | OpenTelemetry architecture, dashboards, log standards | HRD-506 |
| [API-LATENCY-SLOS.md](API-LATENCY-SLOS.md) | Per-endpoint latency budgets (5 services, 35+ endpoints) | HRD-204 |
| [RELEASE-PIPELINE.md](RELEASE-PIPELINE.md) | Staged rollout config, gates, rollback procedure | HRD-702 |
| [soak.js](../load-tests/soak.js) | 24h soak/endurance test config | HRD-904 |
| [regression/run.py](../regression/run.py) | Regression suite runner (cross-service) | HRD-901 |
| [regression/README.md](../regression/README.md) | Regression corpus format + 42 test cases | HRD-901 |

### epic:release-eng (GA blockers)
| # | Title | Track | Status |
|---|-------|------|--------|
| 343 | HRD-706 — Staged rollout + kill-switch/feature flags | devops | ✅ Feature flags config created (feature-flags.json) |
| 342 | HRD-705 — App Store + Play submission | android, ios | 🔴 Open |
| 330 | HRD-704 — Store listings | ux | 🔴 Open |
| 329 | HRD-703 — Play Data Safety + App Store privacy labels | android, ios | 🔴 Open |
| 328 | HRD-702 — Release pipelines — versioned, staged rollout | devops | ✅ Docs created (RELEASE-PIPELINE.md) |

### epic:quality
| # | Title | Track | Status |
|---|-------|------|--------|
| 349 | HRD-903 — Synthetic monitoring (staging + prod) | qa, devops | ✅ Synthetic config created (synthetic.js) |
| 348 | HRD-902 — Cross-device / OS-version matrix | qa | ✅ Matrix docs created (DEVICE-MATRIX.md) |
| 332 | HRD-904 — Soak / endurance test | qa | ✅ Load/soak tests created (soak.js, nutriplan.js) |
| 314 | HRD-901 — Full regression suite across P1–P5 | qa | ✅ Regression runner + corpus created (regression/) |

### epic:security-compliance
| # | Title | Track |
|---|-------|-------|
| 336 | HRD-106 — Pentest remediation + re-test sign-off | backend, devops |
| 335 | HRD-105 — PCI scope final review + attestation | backend, devops |
| 334 | HRD-104 — Account deletion + data export | backend |

### epic:reliability
| # | Title | Track | Status |
|---|-------|------|--------|
| 340 | HRD-505 — Failover / resilience (chaos) test | qa, devops | 🔴 Open |
| 324 | HRD-504 — Backup/restore + disaster-recovery drill | devops | 🔴 Open |
| 323 | HRD-503 — Runbooks + incident-response playbooks | devops | ✅ Playbooks created (INCIDENT-RESPONSE.md) |
| 310 | HRD-506 — Production observability — traces/logs/metrics | backend, devops | ✅ Docs created (OBSERVABILITY.md) |
| 309 | HRD-502 — Alerting + on-call rotation | devops | ✅ Docs created (ALERTING.md) |
| 308 | HRD-501 — SLOs + error budgets per service | devops | ✅ Docs created (SLO-ERROR-BUDGETS.md) |

### epic:performance
| # | Title | Track | Status |
|---|-------|------|--------|
| 318 | HRD-206 — Scalability/capacity plan + autoscaling | devops | 🔴 Open |
| 317 | HRD-205 — Mobile performance — startup, scroll/jank, memory | android, ios | 🔴 Open |
| 316 | HRD-203 — Backend perf tuning (indexes, N+1, pooling, caching) | backend | 🔴 Open |
| 305 | HRD-204 — API latency SLOs + p95/p99 budgets | backend, devops | ✅ Docs created (API-LATENCY-SLOS.md) |
| 304 | HRD-202 — Load + soak test all services | qa, devops | ✅ Load tests created (nutriplan.js, soak.js) |

### epic:accessibility
| # | Title | Track |
|---|-------|-------|
| 338 | HRD-305 — Accessibility regression checks in CI/E2E | qa |
| 337 | HRD-304 — Dynamic type / large-font + contrast pass | android, ios |
| 320 | HRD-303 — Accessibility fixes — iOS/SwiftUI | ios |
| 319 | HRD-302 — Accessibility fixes — Android/Compose | android |
| 306 | HRD-301 — WCAG 2.1 AA audit across all flows | qa, ux |

### epic:beta
| # | Title | Track |
|---|-------|-------|
| 341 | HRD-605 — Crash-free ≥ 99.5% — stabilize top crashes | android, ios |
| 327 | HRD-606 — Beta analytics + funnel/retention instrumentation | backend, devops |
| 326 | HRD-604 — Beta fix loop — triage + prioritize + burn down | qa |
| 325 | HRD-603 — Closed beta launch + feedback intake | qa, devops |
| 312 | HRD-602 — Crash/ANR monitoring (Crashlytics/Sentry) | devops |
| 311 | HRD-601 — TestFlight + Play internal beta pipeline | devops |

### epic:localization
| # | Title | Track |
|---|-------|-------|
| 339 | HRD-404 — In-app legal/content (ToS, privacy) localized | backend, ux |
| 323 | HRD-403 — Store metadata + screenshots localized (es/en) | ux |
| 321 | HRD-402 — Formatting pass — MXN currency, dates, numbers, units | android, ios |
| 307 | HRD-401 — Localization audit — extract, complete es/en, pseudo-loc | kmp, ux |

### epic:design
| # | Title | Track |
|---|-------|-------|
| 333 | HRD-1003 — Store creative — screenshots, preview video, feature graphic | ux |
| 315 | HRD-1002 — Empty / error / loading state audit + fixes | ux |

### epic:performance (duplicate)
| # | Title | Track | Status |
|---|-------|------|--------|
| 318 | HRD-206 — Scalability/capacity plan + autoscaling validation | devops | 🔴 Open |
| 317 | HRD-205 — Mobile performance — startup, scroll/jank, memory (both) | android, ios | 🔴 Open |
| 316 | HRD-203 — Backend perf tuning (indexes, N+1, pooling, caching) | backend | 🔴 Open |
| 305 | HRD-204 — API latency SLOs + p95/p99 budgets per endpoint | backend, devops | ✅ Docs created (API-LATENCY-SLOS.md) |
| 304 | HRD-202 — Load + soak test all services to target RPS | qa, devops | ✅ Load tests created (nutriplan.js, soak.js) |

## Open Issues by Epic

| # | Title | State | Labels |
|---|-------|-------|--------|
| 505 | HRD-905 — Bug bash + triage before GA | OPEN | phase:P1, epic:quality, track:qa, pts:3, phase:P2, phase:P3, sprint-21 | ✅ Docs created (LAUNCH-RUNBOOK.md, GA-GO-LIVE-CHECKLIST.md) |
| 504 | HRD-805 — GA sign-off — SLOs/dashboards green, exit criteria met | OPEN | phase:P1, track:devops, pts:3, phase:P2, phase:P3, epic:launch, sprint-21 | 📋 Tracking issue created |
| 351 | HRD-906 — Release regression gate in CI (block GA on red) | OPEN | phase:P1, epic:quality, track:qa, track:devops, pts:3, phase:P2, phase:P3, sprint-21 | ✅ Done (PR #506 merged) |
| 350 | HRD-905 — Bug bash + triage before GA | OPEN | phase:P1, epic:quality, track:qa, pts:3, phase:P2, phase:P3, sprint-21 | 📋 Tracking issue created |
| 349 | HRD-903 — End-to-end synthetic monitoring (staging + prod) | OPEN | phase:P1, epic:quality, track:qa, track:devops, pts:3, phase:P2, phase:P3, sprint-21 | ✅ Synthetic config created (synthetic.js) |
| 348 | HRD-902 — Cross-device / OS-version matrix (device farm) | OPEN | phase:P1, epic:quality, track:qa, pts:3, phase:P2, phase:P3, sprint-21 | ✅ Matrix docs created (DEVICE-MATRIX.md) |
| 347 | HRD-805 — GA sign-off — SLOs/dashboards green, exit criteria met | OPEN | phase:P1, track:devops, pts:3, phase:P2, phase:P3, epic:launch, sprint-21 |
| 346 | HRD-804 — Legal sign-off — ToS, privacy policy, data processing | OPEN | phase:P1, track:ux, pts:3, phase:P2, phase:P3, epic:launch, sprint-21 |
| 345 | HRD-803 — Support readiness — help center, FAQ, support routing | OPEN | phase:P1, track:ux, pts:3, phase:P2, phase:P3, epic:launch, sprint-21 |
| 344 | HRD-802 — Production cutover + scaling + DNS/CDN readiness | OPEN | phase:P1, track:devops, pts:3, phase:P2, phase:P3, epic:launch, sprint-21 | ✅ Plan created (PRODUCTION-CUTOVER.md) |
| 343 | HRD-706 — Staged production rollout + kill-switch/feature flags | OPEN | phase:P1, track:devops, pts:3, phase:P2, phase:P3, epic:release-eng, sprint-21 | ✅ Feature flags config created (feature-flags.json) |
| 342 | HRD-705 — App Store + Play submission + review responses | OPEN | phase:P1, track:android, track:ios, pts:5, phase:P2, phase:P3, epic:release-eng, sprint-21 |
| 341 | HRD-605 — Crash-free ≥ 99.5% — stabilize top crashes | OPEN | phase:P1, track:android, track:ios, pts:5, phase:P2, phase:P3, epic:beta, sprint-21 |
| 340 | HRD-505 — Failover / resilience (chaos) test on critical paths | OPEN | stretch, phase:P1, track:qa, track:devops, pts:3, phase:P2, phase:P3, epic:reliability, sprint-21 |
| 339 | HRD-404 — In-app legal/content (ToS, privacy) localized + linked | OPEN | phase:P1, track:backend, track:ux, pts:3, phase:P2, phase:P3, epic:localization, sprint-21 |
| 338 | HRD-305 — Accessibility regression checks in CI/E2E | OPEN | phase:P1, track:qa, pts:3, phase:P2, phase:P3, epic:accessibility, sprint-21 |
| 337 | HRD-304 — Dynamic type / large-font + contrast pass (both) | OPEN | phase:P1, track:android, track:ios, pts:3, phase:P2, phase:P3, epic:accessibility, sprint-21 |
| 336 | HRD-106 — Pentest remediation + re-test sign-off | OPEN | phase:P1, track:backend, track:devops, pts:5, phase:P2, phase:P3, epic:security-compliance, sprint-21 |
| 335 | HRD-105 — PCI scope final review + attestation (payments) | OPEN | phase:P1, track:backend, track:devops, pts:3, phase:P2, phase:P3, epic:security-compliance, sprint-21 |
| 334 | HRD-104 — Account deletion + data export (user data rights) | OPEN | phase:P1, track:backend, pts:3, phase:P2, phase:P3, epic:security-compliance, sprint-21 |
| 333 | HRD-1003 — Store creative — screenshots, preview video, feature graphic | OPEN | phase:P1, epic:design, track:ux, pts:3, phase:P2, phase:P3, sprint-21 |
| 332 | HRD-904 — Soak / endurance test (long sessions, leaks) | OPEN | stretch, phase:P1, epic:quality, track:qa, pts:3, phase:P2, phase:P3, sprint-20 | ✅ Load/soak tests created (soak.js, nutriplan.js) |
| 331 | HRD-801 — GA go-live checklist + launch runbook | OPEN | phase:P1, track:devops, pts:3, phase:P2, phase:P3, epic:launch, sprint-20 | ✅ Docs created (LAUNCH-RUNBOOK.md, GA-GO-LIVE-CHECKLIST.md) |
| 330 | HRD-704 — Store listings — copy, categories, age rating, creative | OPEN | phase:P1, track:ux, pts:3, phase:P2, phase:P3, epic:release-eng, sprint-20 |
| 329 | HRD-703 — Play Data Safety + App Store privacy nutrition labels | OPEN | phase:P1, track:android, track:ios, pts:3, phase:P2, phase:P3, epic:release-eng, sprint-20 |
| 328 | HRD-702 — Release pipelines — versioned, staged rollout (both) | OPEN | phase:P1, track:devops, pts:5, phase:P2, phase:P3, epic:release-eng, sprint-20 |
| 327 | HRD-606 — Beta analytics + funnel/retention instrumentation | OPEN | phase:P1, track:backend, track:devops, pts:3, phase:P2, phase:P3, epic:beta, sprint-20 |
| 326 | HRD-604 — Beta fix loop — triage + prioritize + burn down | OPEN | story, track:qa, pts:5, phase:P6, epic:beta, sprint-20 |
| 325 | HRD-603 — Closed beta launch + feedback intake | OPEN | story, track:qa, track:devops, pts:3, phase:P6, epic:beta, sprint-20 |
| 324 | HRD-504 — Backup/restore + disaster-recovery drill | OPEN | story, track:devops, pts:3, phase:P6, epic:reliability, sprint-20 |
| 323 | HRD-503 — Runbooks + incident-response playbooks | OPEN | story, track:devops, pts:3, phase:P6, epic:reliability, sprint-20 | ✅ Playbooks created (INCIDENT-RESPONSE.md) |
| 322 | HRD-403 — Store metadata + screenshots localized (es/en) | OPEN | story, track:ux, pts:3, phase:P6, epic:localization, sprint-20 |
| 321 | HRD-402 — Formatting pass — MXN currency, dates, numbers, units (both) | OPEN | story, track:android, track:ios, pts:3, phase:P6, epic:localization, sprint-20 |
| 320 | HRD-303 — Accessibility fixes — iOS/SwiftUI | OPEN | story, track:ios, pts:5, phase:P6, epic:accessibility, sprint-20 |
| 319 | HRD-302 — Accessibility fixes — Android/Compose | OPEN | story, track:android, pts:5, phase:P6, epic:accessibility, sprint-20 |
| 318 | HRD-206 — Scalability/capacity plan + autoscaling validation | OPEN | story, track:devops, pts:3, phase:P6, epic:performance, sprint-20 |
| 317 | HRD-205 — Mobile performance — startup, scroll/jank, memory (both) | OPEN | story, track:android, track:ios, pts:5, phase:P6, epic:performance, sprint-20 |
| 316 | HRD-203 — Backend perf tuning (indexes, N+1, pooling, caching) | OPEN | story, track:backend, pts:5, phase:P6, epic:performance, sprint-20 |
| 315 | HRD-1002 — Empty / error / loading state audit + fixes | OPEN | story, epic:design, track:ux, pts:3, phase:P6, sprint-20 |
| 314 | HRD-901 — Full regression suite across P1–P5 journeys | OPEN | story, epic:quality, track:qa, pts:5, phase:P6, sprint-19 | ✅ Regression runner + corpus created (regression/) |
| 313 | HRD-701 — App signing + release config (Play App Signing, ASC) | OPEN | story, track:devops, pts:3, phase:P6, epic:release-eng, sprint-19 |
| 312 | HRD-602 — Crash/ANR monitoring (Crashlytics/Sentry) + dashboards | OPEN | story, track:devops, pts:3, phase:P6, epic:beta, sprint-19 |
| 311 | HRD-601 — TestFlight + Play internal beta pipeline + tester groups | OPEN | story, track:devops, pts:3, phase:P6, epic:beta, sprint-19 |
| 310 | HRD-506 — Production observability — traces/logs/metrics completeness | OPEN | story, track:backend, track:devops, pts:3, phase:P6, epic:reliability, sprint-19 | ✅ Docs created (OBSERVABILITY.md) |
| 309 | HRD-502 — Alerting + on-call rotation (paging) | OPEN | story, track:devops, pts:3, phase:P6, epic:reliability, sprint-19 | ✅ Docs created (ALERTING.md) |
| 308 | HRD-501 — SLOs + error budgets per service + dashboards | OPEN | story, track:devops, pts:3, phase:P6, epic:reliability, sprint-19 | ✅ Docs created (SLO-ERROR-BUDGETS.md) |
| 307 | HRD-401 — Localization audit — extract, complete es/en, pseudo-loc | OPEN | story, track:kmp, track:ux, pts:5, phase:P6, epic:localization, sprint-19 |
| 306 | HRD-301 — WCAG 2.1 AA audit across all flows (both apps) | OPEN | story, track:qa, track:ux, pts:5, phase:P6, epic:accessibility, sprint-19 |
| 305 | HRD-204 — API latency SLOs + p95/p99 budgets per endpoint | OPEN | story, track:backend, track:devops, pts:3, phase:P6, epic:performance, sprint-19 | ✅ Docs created (API-LATENCY-SLOS.md) |
| 304 | HRD-202 — Load + soak test all services to target RPS; find breakpoints | OPEN | story, track:qa, track:devops, pts:5, phase:P6, epic:performance, sprint-19 | ✅ Load tests created (nutriplan.js, soak.js) |
