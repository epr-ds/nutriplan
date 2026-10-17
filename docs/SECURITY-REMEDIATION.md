# Pentest Remediation & Re-Test Sign-Off

## Purpose

Record for **HRD-106 (#336)**: the disposition of the high/critical finding classes raised by the
**HRD-101 external penetration test (#300)**, the control that remediates each one, and the
automated **re-test** that confirms closure.

This is the evidence document referenced by the Security sections of the
[GA launch runbook](LAUNCH-RUNBOOK.md) and the [GA go-live checklist](GA-GO-LIVE-CHECKLIST.md).
The external tester's report itself is retained by Security; this register tracks the classes and
their remediation status inside the repository so the closure is reviewable and re-runnable.

## Scope

The API surface (Identity, Commerce, Dietary, AI, Notification) and the signed Android/iOS clients
that consume it.

## Severity scale

| Severity | Definition |
|----------|------------|
| Critical | Remote, unauthenticated compromise of accounts, money, or data. |
| High | Authenticated privilege/ownership escalation, authentication bypass, or injection of trust. |
| Medium | Information disclosure or abuse requiring a privileged position. |
| Low | Hardening/defence-in-depth gaps with no direct exploitation path. |

## Findings register

Every high/critical class from the pentest is **Remediated** and pinned by an automated regression
test. Each service's `tests/test_security.py` (and the service suites named below) is re-run by the
[`Security re-test` gate](#re-test-gate) on every change.

| Finding class | OWASP API (2023) | Sev | Status | Remediation control | Re-test evidence |
|---------------|------------------|-----|--------|---------------------|------------------|
| Forged access tokens / algorithm confusion (`alg=none`, HS256-signed-with-public-key) | API2 Broken Authentication | High | Remediated | RS256 signature pinned; token header `alg` is never trusted; signing key resolved by `kid` from JWKS | `services/*/app/core/security.py`; `tests/test_security.py::test_verify_rejects_bad_signature`, `notification/…::test_verify_rejects_a_token_signed_with_an_unexpected_algorithm`, `identity/…::test_users_me_rejects_alg_none_token`, `identity/…::test_users_me_rejects_foreign_key_signature` |
| Cross-service token replay via wrong audience/issuer or expiry | API2 Broken Authentication | High | Remediated | `iss`/`aud`/`exp` claims enforced on every request; each service validates against the shared issuer/audience | `tests/test_security.py::test_verify_rejects_wrong_audience` / `::test_verify_rejects_wrong_issuer` / `::test_verify_rejects_expired_token`; `identity/tests/test_security.py::test_users_me_rejects_wrong_audience` / `::test_users_me_rejects_expired_token` |
| Credential stuffing / brute force against auth | API2 / API4 | High | Remediated | Per-IP sliding-window throttle on `/auth/*` plus failed-login lockout; per-user throttle + CORS allow-list at the AI and Notification edges | `services/identity/app/core/ratelimit.py`, `config.login_max_failed_attempts`; `identity/tests/test_ratelimit.py`, `identity/tests/test_auth.py`; `services/{ai,notification}/app/core/ratelimit.py` + `tests/test_ratelimit.py`, `notification/tests/test_edge.py` |
| Account enumeration on login | API2 Broken Authentication | High | Remediated | Unknown-email and wrong-password responses are indistinguishable (same status + message) | `identity/tests/test_security.py::test_login_does_not_reveal_whether_email_exists` |
| Weak password storage | API2 Broken Authentication | High | Remediated | Argon2id hashing (memory-hard) via `argon2-cffi` | `identity/tests/test_security.py::test_password_hash_is_argon2id_and_verifies` |
| Broken object level authorization / IDOR on orders and user data | API1 BOLA | High | Remediated | Owner-scoped repositories + required `CurrentPrincipal` dependency; preferences and feed scoped to the JWT subject | `services/commerce/tests/test_ownership_api.py`; `services/notification/tests/test_preferences_api.py`, `test_notifications_api.py` |
| Forged inbound payment & kitchen webhooks | API10 Unsafe Consumption | High | Remediated | HMAC-SHA256 over the raw request body with a shared secret and constant-time compare | `services/commerce/app/adapters/kitchen_webhook_verifier.py`, `services/commerce/app/payments/provider.py`; `commerce/tests/test_kitchen_webhook.py`, `test_payment_webhook.py` |
| Prompt injection / unsafe LLM output | LLM01 Prompt Injection | High | Remediated | Input sanitizer + policy/compliance guardrails; out-of-bounds and allergen responses blocked | `services/ai/tests/test_guardrails_sanitizer.py`, `test_guardrails_policy.py`, `test_guardrails_compliance.py`, `test_guardrails_adversarial.py`; gating `guardrails.yml` job |
| Malformed / over-posted request bodies (mass assignment) | API3 / API1 | High | Remediated | Pydantic v2 typed schemas; requests and responses validated against the OpenAPI contract in CI | `services/*/app/api/schemas.py`; `services/*/tests/test_contract.py` |
| Unrestricted resource consumption / DoS | API4 | High | Remediated | Bounded per-user request rate (429 + `Retry-After`); AI token/spend budget guard; per-route limits disable probes | `services/{ai,notification,identity}/app/core/ratelimit.py`; `services/ai/tests/test_budget_guard.py`; `tests/test_ratelimit.py` |
| Permissive CORS | API8 Misconfiguration | High | Remediated | CORS applied only when an explicit allow-list is configured (default: no cross-origin headers) | `services/{ai,notification}/app/main.py`; `services/ai/tests/test_cors.py`, `notification/tests/test_edge.py::test_no_cors_headers_without_an_allow_list` |
| Secret leakage in the repository/history | API8 Misconfiguration | High | Remediated | `gitleaks` secret scan on every change; `.env` git-ignored; webhook/JWT secrets typed as `SecretStr` and injected from the vault | `.github/workflows/security.yml`, `SECURITY.md`, `services/commerce/app/core/config.py` |

## Residual risk (accepted & recorded)

| Ref | Residual risk | Severity | Justification / compensating control | Owner | Review |
|-----|---------------|----------|--------------------------------------|-------|--------|
| R-01 | No application-layer security headers (HSTS, `X-Content-Type-Options`, CSP) | Low | TLS is terminated and hardening headers are applied at the edge/gateway; services return JSON only and never render HTML | Security Lead | Next pentest |
| R-02 | Rate-limit state is process-local, so the effective limit scales with replica count | Medium | Per-instance limits still bound abuse; a shared (Redis-backed) limiter is the production hardening follow-up; gateway limiting is the primary control | Backend Lead | Before GA |
| R-03 | Trust in third-party payment/grocery providers | Low | Card data is tokenized by the provider — the platform never stores a PAN; provider callbacks are signature-verified | Security Lead | Next pentest |

## Re-test gate

The `Security re-test` job in [`.github/workflows/security.yml`](../.github/workflows/security.yml)
re-runs each service's security regression suite as a **named, gating** check on every push and pull
request, so a remediated finding cannot silently regress:

```
pytest tests/test_security.py      # per service: identity, commerce, dietary, notification
```

Closure rule: a finding class is considered closed when its row above is `Remediated` **and** the
`Security re-test` job is green on `main`. A red gate reopens the class.

## Sign-off

| Role | Name | Date | Sign-off |
|------|------|------|----------|
| Engineering Lead | | | |
| Security Lead | | | |
| Product Owner | | | |

## References

- [HRD-101: External penetration test (#300)](https://github.com/epr-ds/nutriplan/issues/300)
- [HRD-106: Pentest remediation + re-test sign-off (#336)](https://github.com/epr-ds/nutriplan/issues/336)
- [SECURITY.md](../SECURITY.md)
- [GA Launch Runbook](LAUNCH-RUNBOOK.md) · [GA Go-Live Checklist](GA-GO-LIVE-CHECKLIST.md)
