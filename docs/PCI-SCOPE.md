# PCI Scope — Payment Flow (SAQ-A)

**Owner:** Security Lead · **Issue:** HRD-105 (#335) · **Review date:** 2026-10-28 · **Status:** Attested

## Scope

This register attests the PCI Data Security Standard (PCI-DSS) scope for Nutriplan's payment
handling. Following the payment security review (COM-809, PR #699) and the tokenization design
(COM-202/203/204/205/206), the platform processes **no card data**.

## Payment flow under SAQ-A

1. The mobile client tokenizes the card with the provider (Stripe/Conekta/PayPal) and sends only the
   opaque provider token (`tok_*`, `paypal_*`, …) plus display metadata to Nutriplan.
2. Nutriplan charges the token at order creation (COM-202) or issues an async instrument
   (OXXO voucher / SPEI transfer / PayPal approval, COM-203/204/205) and settles via signed provider
   webhooks (COM-206).
3. Nutriplan persists only the provider token, provider charge id, references and amounts — never a
   PAN, CVV or raw card number (enforced by the gateway boundary regressions in
   `services/commerce/tests/test_payment_security_regression.py` and
   `services/commerce/tests/test_pci_scope.py`).

## SAQ-A attestation

Because no PAN is stored, processed or transmitted through Nutriplan's servers, the payment flow is
attested against **SAQ-A** (the most minimal PCI-DSS scope applicable to entities that use
tokenizing payment processors and never touch card data).

- [x] No PAN on our servers / logs — re-verified via payment security regression suite (HRD-105).
- [x] Tokenization paths re-verified — gateway rejects raw PANs as tokens; charges persist only
      provider handles (COM-809, PR #699).
- [x] SAQ-A scope documented + attested — this document.

## Review history

| Date | Reviewer | Outcome |
|------|----------|---------|
| 2026-10-28 | Security Lead | Attested — SAQ-A applicable; no PAN in Nutriplan systems |