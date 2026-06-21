# 1. Record architecture decisions

- Status: Accepted
- Date: 2026-06-20

## Context

We need a lightweight, durable way to capture significant architecture decisions and the
reasoning behind them, so future contributors understand *why* the system is the way it is.

## Decision

We will use **Architecture Decision Records (ADRs)** — short Markdown files in
`docs/architecture/adr/`, numbered sequentially. Each records the context, the decision, and
its consequences. The format follows Michael Nygard's ADR template.

## Consequences

- Every significant, hard-to-reverse decision gets an ADR, raised as part of the PR that
  implements it.
- ADRs are immutable once accepted; a later ADR can supersede an earlier one.
