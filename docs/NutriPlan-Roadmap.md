# NutriPlan — Phased Development Roadmap

> Spec-driven roadmap derived from the NutriPlan DDD specification (Identity, Dietary
> Planning, Commerce, Notification + AI contexts). Platform: **Kotlin Multiplatform (KMP)**
> with a shared domain/data/network layer and native-feel UI (Compose Multiplatform on
> Android, SwiftUI on iOS).

---

## 0. Planning Assumptions

These shape the estimates below. Tell me if any are wrong and I'll re-baseline.

| # | Assumption | Impact if changed |
|---|------------|-------------------|
| A1 | **Greenfield** build, no legacy migration | Adds discovery/migration time |
| A2 | **MVP-first**, then expand context-by-context | Big-bang launch is slower & riskier |
| A3 | Startup-scale core team (~10 FTE), co-located/remote-hybrid | Smaller team ⇒ longer; larger ⇒ coordination cost |
| A4 | Target market **Mexico** (MXN, OXXO/SPEI, `es` default) per spec | Multi-region adds localization/compliance |
| A5 | KMP shared logic; **Compose Multiplatform for Android, SwiftUI for iOS** | Compose-MP-for-iOS changes iOS staffing |
| A6 | Backend = microservices as specced (Postgres/Mongo/Redis), single cloud (e.g. AWS/GCP) | Monolith-first would cut Phase 0–2 time |
| A7 | LLM via hosted API (OpenAI/Anthropic/Vertex) with caching, not self-hosted | Self-hosting adds an ML-ops workstream |
| A8 | 2-week sprints; estimates are **calendar weeks at ~80% capacity** | — |

---

## 1. Team Composition

**Core team (steady state ≈ 10 FTE):**

| Role | Count | Primary scope |
|------|-------|---------------|
| Eng Lead / Mobile Architect | 1 | Architecture, KMP shared module, code review, ADRs |
| Mobile Engineers (KMP) | 2 | Compose + SwiftUI UI, ViewModels, use cases, local DB |
| Backend Engineers | 2 | Identity, Dietary, Commerce, Notification services + gateway |
| AI/ML Engineer | 1 | AI service (FastAPI), prompts, guardrails, nutrition scoring |
| QA / SDET | 1 | Test strategy, automation, contract & E2E tests |
| Product Designer (UX/UI) | 1 | Design system, flows, prototypes, accessibility |
| Product Manager | 1 | Backlog, prioritization, stakeholder/provider liaison |
| DevOps / Platform | 0.5–1 | CI/CD, IaC, K8s, observability, secrets |

**Scale-up additions (from Phase 4):** +1 backend (commerce/integrations), +1 mobile, +0.5 data engineer (analytics/recipe data), fractional security reviewer.

---

## 2. Architecture Recap (build targets)

- **Mobile (KMP):** Clean Architecture — `presentation` (Compose/SwiftUI + MVVM) → `domain` (use cases, models) → `data` (repositories, Ktor API clients, SQLDelight local DB). Shared module holds domain + data + DTOs.
- **Backend:** API Gateway (Kong/Traefik) → Identity (Postgres), Dietary (MongoDB), Commerce (Postgres), Notification (Redis), AI (Python/FastAPI). Event-driven integration via a message bus (e.g. Kafka/NATS) for domain events.
- **Cross-cutting:** OpenAPI 3.0 contracts → client/server codegen; JWT auth; observability (OTel/Grafana); anti-corruption layers for external grocery/payment providers.

---

## 3. Phase Roadmap

Legend: **P** = phase, sprints are 2 weeks. Parallelizable work is noted per phase.

### P0 — Discovery & Foundation · Sprints 1–2 · ~4 wks
**Goal:** Everything needed to start feature work safely.
- Finalize OpenAPI contracts (Identity/Dietary/Commerce) + codegen pipeline.
- Architecture Decision Records: KMP UI strategy, message bus, AI provider, payment provider.
- Repos + monorepo layout, CI/CD, dev/stage/prod environments, IaC baseline.
- KMP project skeleton (shared module, DI, networking, SQLDelight); backend service scaffolds + gateway.
- Design system v0 (tokens, typography, core components), key flow wireframes.
- **Exit:** "Hello world" request flows mobile → gateway → a stub service in CI; design system in Figma.

### P1 — Identity & Onboarding (MVP) · Sprints 3–5 · ~6 wks
**Goal:** A user can sign up, log in, and configure dietary preferences.
- Identity service: register, login, OAuth (Google/Apple/Facebook), `/users/me`, dietary-preferences; Postgres schema; JWT + refresh tokens.
- Mobile: auth screens, OAuth integration, onboarding (diet type, allergies, calorie/macro targets, cuisine prefs), profile; secure token storage; auth interceptor.
- QA: contract tests for Identity, auth E2E.
- **Exit:** End-to-end authenticated session on both platforms; preferences persisted.

### P2 — Dietary Planning Core · Sprints 6–9 · ~8 wks
**Goal:** Users create and view meal plans with real nutrition data.
- Dietary service (MongoDB): meal plan CRUD, add-meal, recipe repository + search, nutrition calculator.
- Domain: `MealPlan` aggregate, `PlannedMeal`, `SatisfactionLevel`, nutritional targets/progress.
- Mobile: meal-plan list/detail/create, meal cards, nutritional progress UI, satisfaction selector, recipe search.
- Seed recipe dataset (curated) for launch.
- **Exit:** Create a multi-day plan, add meals, see nutritional summary & progress.

### P3 — AI Advisor · Sprints 10–12 · ~6 wks *(can start in S9, overlapping P2 once domain models stabilize)*
**Goal:** AI-powered recommendations, meal analysis, plan optimization.
- AI service (FastAPI + LLM): `/ai/recommendations`, `/ai/analyze-meal`, `/ai/optimize-plan`; prompt engineering, JSON-schema-constrained outputs, nutritional-alignment scoring.
- Guardrails: allergy/exclusion enforcement, calorie/macro bounds, hallucination fallback to curated recipes; response caching + cost controls.
- Mobile: AI recommendation screen, optimize-plan flow, reasoning display.
- **Exit:** Recommendations respect dietary constraints; optimize improves a draft plan measurably.

### P4 — Commerce & Fulfillment · Sprints 13–17 · ~10 wks
**Goal:** Turn a plan into a paid, fulfilled order.
- Commerce service (Postgres): order create/list/detail/cancel; pricing; order state machine.
- Fulfillment: dark-kitchen availability; grocery provider integrations (FreshBasket/Walmart/Chedraui) behind anti-corruption layer with circuit breakers + provider fallback.
- Payments: provider integration (Stripe/Conekta) — cards, **OXXO, SPEI**, PayPal; tokenization (no PAN on our servers).
- Mobile: checkout, address & payment management, order detail, order tracking.
- **Exit:** Place a real (sandbox) order via dark kitchen and grocery paths; payment + tracking working.

### P5 — Notifications & Eventing · Sprints 16–18 · ~4 wks *(overlaps P4)*
**Goal:** Timely, reliable status updates.
- Notification service (Redis) + push (FCM/APNs); event-driven order-status & plan reminders via message bus; deep links.
- **Exit:** Order lifecycle and plan reminders deliver as push + in-app, idempotently.

### P6 — Hardening, Beta & Launch · Sprints 19–21 · ~6 wks
**Goal:** Production-ready GA.
- Security review + pen test; load/perf testing; accessibility (WCAG) pass; localization (`es`/`en`).
- Closed beta (TestFlight / Play internal) → fix loop; crash-free ≥ 99.5% target.
- App Store / Play submission, privacy/data compliance, runbooks & on-call.
- **Exit:** GA on both stores; SLOs and dashboards green.

---

## 4. Timeline at a Glance

```
Month:        1     2     3     4     5     6     7     8     9     10
Sprint:    S1-2  S3-4  S5-6  S7-8  S9-10 S11-12 S13-14 S15-16 S17-18 S19-21
P0  ███
P1     ██████
P2           ████████████
P3                 ████████   (overlaps tail of P2)
P4                         ████████████████
P5                              ██████        (overlaps P4)
P6                                        ████████
                                                   ▲ GA
```

- **~21 sprints ≈ 42 weeks ≈ ~10 months to GA.**
- **Private beta** (auth + planning) shippable around **end of Month 4–5** (after P2).

---

## 5. Critical Path & Dependencies

```
P0 ─▶ P1 (Identity) ─▶ P2 (Dietary) ─┬─▶ P3 (AI)
                                      └─▶ P4 (Commerce) ─▶ P5 (Notifications) ─▶ P6 (Launch)
```

- **Identity blocks everything** (all services need auth).
- **Dietary blocks AI and Commerce** (orders are built from meal plans; AI optimizes plans).
- **AI can run partly in parallel** with late P2 once domain models freeze.
- **Notifications depend on Commerce** events but can be scaffolded earlier.

---

## 6. Estimates Summary

| Phase | Scope | Calendar | Sprints |
|-------|-------|----------|---------|
| P0 | Foundation | 4 wks | 1–2 |
| P1 | Identity & Onboarding | 6 wks | 3–5 |
| P2 | Dietary Planning | 8 wks | 6–9 |
| P3 | AI Advisor | 6 wks | 10–12 (overlap) |
| P4 | Commerce & Fulfillment | 10 wks | 13–17 |
| P5 | Notifications | 4 wks | 16–18 (overlap) |
| P6 | Hardening & Launch | 6 wks | 19–21 |
| **Total (with overlap)** | **MVP → GA** | **~10 months** | **21** |

**Fast-track MVP option (~5 months):** Ship P0 → P1 → P2 → a trimmed P4 (digital plan + **single** grocery provider, cards-only) and **defer** AI optimization, dark kitchen, and multi-provider to a fast-follow. Cuts ~4–5 months to first revenue.

---

## 7. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| LLM cost / latency / hallucination | High | High | Caching, JSON-schema outputs, allergy guardrails, curated fallback recipes, budget caps |
| External grocery API reliability/contracts | Med | High | Anti-corruption layer, circuit breakers, provider fallback, start integration in P0 spikes |
| Payment compliance (PCI, OXXO/SPEI) | Med | High | Use tokenizing provider (Conekta/Stripe), never store PAN, early legal review |
| KMP iOS UI maturity / dual-UI cost | Med | Med | Lock UI strategy in P0 ADR; share logic, keep UI thin |
| Nutritional accuracy & liability | Med | High | Verified data sources, medical disclaimers, no health claims |
| Scope creep across 4 contexts | High | Med | Strict MVP gating, phase exit criteria, fast-track option |
| Recipe data cold-start | Med | Med | Curate seed dataset in P2; AI augments, doesn't replace |
| OAuth/Apple review friction | Low | Med | Implement Sign-in-with-Apple early, follow store guidelines |

---

## 8. Milestones & Exit Criteria

| Milestone | When | Definition of Done |
|-----------|------|--------------------|
| **M1 — Foundation** | Wk 4 | CI/CD green, contracts codegen'd, app shell calls a service |
| **M2 — Auth Beta** | Wk 10 | Sign up/in + onboarding on both platforms |
| **M3 — Planning Usable** | Wk 18 | Create plan, add meals, nutrition summary; **private beta** |
| **M4 — AI Live** | Wk 24 | Constraint-respecting recommendations + optimize |
| **M5 — Commerce** | Wk 34 | Sandbox order + payment + tracking, dark kitchen & grocery |
| **M6 — GA** | Wk 42 | Stores approved, SLOs met, crash-free ≥ 99.5% |

---

## 9. Engineering Standards (apply every phase)

- **Definition of Done:** code reviewed, unit + contract tests, OpenAPI in sync, telemetry added, accessibility checked, feature-flagged.
- **Quality gates:** ≥70% coverage on domain/use-case layers; contract tests block deploy on breaking API changes.
- **Observability:** structured logs, traces, per-service dashboards & alerts from day one.
- **Security:** secrets in vault, JWT rotation, dependency scanning, threat-model review before P4.

---

*Next options: (a) I can expand any phase into a sprint-by-sprint backlog with epics/stories, (b) produce a leaner fast-track-only plan, or (c) load these phases into the session task tracker.*
