# Flaky-Test Policy

## Purpose

Prevent flaky tests from masking real regressions and eroding CI trust.

## Rules

1. **Detection** — Any test that fails non-deterministically (passes on re-run without code change) is flagged as flaky.
2. **Quarantine** — Flaky tests are marked with `@pytest.mark.flaky` and excluded from the default test run (`pytest -m "not flaky"`). They run in a nightly scheduled job.
3. **Triaging** — Flaky tests must be triaged within 48 hours. The owner files a bug and commits a fix within one sprint.
4. **Escalation** — A test that flakes 3+ times in a sprint is auto- quarantined and blocks the release until fixed.
5. **Monitoring** — CI dashboards track flakiness rate per suite. A rate > 1 % triggers a hardening sprint.

## Implementation

- Mark flaky tests: `@pytest.mark.flaky(reason="reason", runs=3)`
- Exclude from CI: `pytest -m "not flaky"`
- Nightly run: `pytest -m flaky`
