# 2. Use a monorepo

- Status: Accepted
- Date: 2026-06-20

## Context

NutriPlan spans a Kotlin Multiplatform mobile app, several backend services, and the OpenAPI
contracts that bind them. A single contract change frequently ripples into both the mobile
client and a service.

## Decision

We will use a **monorepo**. Mobile, services, contracts, and infrastructure live in one
repository. Services remain independently deployable through **path-filtered CI/CD pipelines**.

## Consequences

- Cross-cutting changes (contract + client + service) are atomic in a single PR.
- One source of truth for API contracts; unified tooling and CI.
- Requires path filtering in CI to avoid rebuilding everything on every change.
- May require a build tool with good monorepo support (Gradle today; Nx/Bazel if scale demands).
