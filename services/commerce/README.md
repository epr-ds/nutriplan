# Commerce Service

**Bounded context:** Commerce. Orders, fulfillment (dark kitchen / grocery), external
provider integration (FreshBasket/Walmart/Chedraui), and payments (cards, PayPal, OXXO, SPEI).

- **Datastore:** PostgreSQL
- **API contract:** [`contracts/commerce.openapi.yaml`](../../contracts/commerce.openapi.yaml)
- **Integration:** external providers sit behind an anti-corruption layer with circuit breakers.

> ⚙️ **Framework TBD (Phase 0 ADR).** Implemented in Phase 4.
