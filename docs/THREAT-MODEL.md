# Commerce Threat Model — STRIDE Review (Order / Payment / Fulfillment)

**Issue:** COM-908 (#241) · **Epic:** E9 · Platform, Payments-Sec & Observability · **Status:** Attested
**Owner:** Security Lead · **Review date:** 2026-10-28 · **Sign-off version:** 1.0

## Scope

This register records the STRIDE (Spoofing, Tampering, Repudiation, Information disclosure, Denial of
service, Elevation of privilege) threat-model review of the Nutriplan commerce surfaces — order
creation and payment, fulfillment (grocery provider fan-out), webhook settlement — and the findings
register plus pre-launch sign-off that go with it.

The payment security invariants under test (no raw PAN, tokenization boundary, HMAC webhook
signature, idempotency) are re-verified by the automated suites in
`services/commerce/tests/test_payment_security_regression.py` (COM-809) and
`services/commerce/tests/test_threat_model.py` (COM-908).

## Surfaces under review

| Surface | Primary flows | Security-relevant seams |
|---|---|---|
| Payment | Card charge at order creation, async instruments (OXXO/SPEI/PayPal), webhook settlement | Provider token boundary, provider charge id, idempotency key, HMAC webhook signature |
| Order | Order state machine (pending → confirmed / cancelled / refunded), status exposure | Owner-scoped reads/writes, no enumeration, state transitions |
| Fulfillment | Grocery provider fan-out (search/place), circuit breaker + fallback, slot reservation | Provider ACL, healthy-provider fallback, `GroceryProviderUnavailableError` normalization |

## STRIDE findings

| Threat | Surface | Mitigation | Status |
|---|---|---|---|
| Spoofing | Payment / Order | Bearer JWT verified (RS256, pinned `alg`, audience/issuer checks) before any proxy; gateway rejects invalid tokens before proxying | Mitigated |
| Tampering | Webhook | HMAC-SHA256 over the raw body with a shared secret, constant-time compare; signature verified before processing | Mitigated |
| Repudiation | Order | Idempotency keys persist `(user, key) → outcome`; deterministic request fingerprints | Mitigated |
| Information disclosure | Payment | No PAN/CVV ever accepted or stored; only opaque provider token + charge id persisted; token never projected to API | Mitigated |
| Denial of service | Fulfillment | Per-provider circuit breakers, per-provider timeouts, provider fallback | Mitigated |
| Elevation of privilege | Order | Owner-scoped aggregates; unknown/other-owner ids indistinguishable (no enumeration) | Mitigated |

## Findings register

| Finding | Severity | Disposition | Tracking |
|---|---|---|---|
| Raw PAN accepted as a payment token at the gateway boundary | High | Remediated (COM-809) — `looks_like_pan` enforcement at schema + use case, regression suite | Closed |
| Payment secrets in plaintext config | High | Remediated (COM-904) — per-env vault + PCI-aware config | Closed |
| Provider fan-out fallback / circuit behavior | Medium | Remediated (COM-407) — breaker + fallback tested | Closed |
| Tokenization boundary violations | High | Remediated (COM-809) — regression suite green | Closed |

## Sign-off

- [x] STRIDE review of order / payment / fulfillment completed (2026-10-28).
- [x] Findings tracked to closure (all listed findings remediated and re-tested).
- [x] Sign-off recorded (2026-10-28, Security Lead) — commerce threat model attested, PCI scope
      attested separately via `docs/PCI-SCOPE.md` (HRD-105). No open HIGH/CRITICAL commerce findings.

**Sign-off:** ✅ Recorded — 2026-10-28 — Security Lead.