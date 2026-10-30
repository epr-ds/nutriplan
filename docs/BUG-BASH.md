# Bug Bash Plan — HRD-905 (Issue #505)

> **Issue:** HRD-905 — Bug bash + triage before GA
> **Epic:** E9 · Quality — Regression & E2E Hardening
> **Sprint:** 21

## 1. Objective

Run the final org-wide bug bash session to catch defects that automated regression,
contract, and chaos tests missed, then triage and severity-tag findings (P0–P3) before
GA sign-off.

## 2. Bug Bash Scope (areas to probe)

The 2-hour bug bash targets **manual, exploratory probing** across the highest-risk
user journeys. Automated suites (unit / regression / contract / chaos) remain the primary
safety net; the bug bash closes the gap they cannot reach.

### In scope (probe areas)

| Area | Specific journeys / surfaces |
|------|------------------------------|
| Mobile — Auth / Identity | Login, signup, OAuth (Google), password reset, session expiry, biometric/enrollment |
| Mobile — Onboarding | First-run flow, permission requests, tutorial steps |
| Mobile — Meal Planning | Create/edit/delete meal plans, meal CRUD, day planning |
| Mobile — Recipes | Search, favorites, detail, filters |
| Mobile — Checkout / Commerce | Cart, slot booking, payment, failure/retry, refunds, webhook handling |
| Mobile — Notifications | In-app, push, deep links |
| Mobile — AI Advisor | Meal analysis, plan optimization, safety guardrails, fallback |
| Mobile — Profile / Settings | Account data, notification prefs, export/delete |
| Backend — Service APIs | Identity, dietary, commerce, notification, ai (per-service regression corpora) |
| Contracts | Cross-service API contract drift checks |

### Out of scope (for this bug bash window)

- Fixing defects (fixes happen post-triage during burn-down).
- New feature development.
- Performance tuning beyond obvious latency regressions surfaced during probing.

## 3. Defect Capture Format

Defects found during the bug bash are captured using the existing GitHub bug template
(`.github/ISSUE_TEMPLATE/bug_report.yml`) to stay consistent:

- **Area** — one of: mobile (Android), mobile (iOS), mobile (shared), service:identity,
  service:dietary, service:commerce, service:notification, service:ai, contracts, infra/CI.
- **What happened** — clear description + expected behavior.
- **Steps to reproduce** — numbered steps.
- **Environment** — device/OS, app version or commit SHA, service version.

Triage adds the **severity tag** and owner metadata:

| Tag | Meaning | Deadline | Burn-down gate |
|-----|---------|----------|----------------|
| P0 | Crash / data loss / security | Must fix before GA | Blocking GA |
| P1 | Major feature broken | Must fix before GA | Blocking GA |
| P2 | Minor feature broken | Fix within 1 week | Non-blocking |
| P3 | Cosmetic / nice-to-have | Backlog | Non-blocking |

Triage fields recorded per defect: severity (P0–P3), assignee owner, fix deadline.

## 4. Tooling & Process

1. **Pre-bug-bash automated gates** (run before/during session):
   - Regression suite: `regression/` + CI `regression.yml` workflow.
   - Contract checks: `scripts/check_mobile_*_contract.py`.
   - Chaos/resilience probes: `chaos-tests/`.
2. **Bug bash session**:
   - 2-hour session with engineering, QA, product.
   - Probing areas listed in §2.
   - Capture defects using §3 format.
3. **Post-bug-bash triage**:
   - Severity tag (P0–P3), assign owner, set deadline.
   - Link findings to follow-up issues where not fixed immediately.
4. **Burn down blockers**:
   - All P0/P1 defects fixed before GA sign-off (HRD-805).

## 5. Acceptance Criteria (HRD-905)

- [ ] Org-wide bug bash session completed.
- [ ] Triage + severity + GA-blocker tagging performed.
- [ ] Blockers burned down (all P0/P1 fixed before GA sign-off).

## 6. Verification for Task-1

This task is complete when the written bug-bash plan doc (`docs/BUG-BASH.md`) exists and
defines: bug bash scope (§2), defect capture format (§3), and tooling/process (§4).