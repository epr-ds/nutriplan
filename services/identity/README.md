# Identity Service

**Bounded context:** Identity. Authentication, OAuth (Google/Facebook/Apple), JWT issuance,
user profile, and dietary preferences.

- **Datastore:** PostgreSQL
- **API contract:** [`contracts/identity.openapi.yaml`](../../contracts/identity.openapi.yaml)

> ⚙️ **Framework TBD (Phase 0 ADR).** The JVM service stack (e.g. Kotlin + Ktor vs. Spring
> Boot) is an open architecture decision recorded in `docs/architecture/adr/`. This directory
> holds the contract and responsibilities until the implementation lands in Phase 1.
