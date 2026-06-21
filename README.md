<div align="center">

# 🥗 NutriPlan

**AI-powered meal planning, dietary tracking, and multi-channel fulfillment.**

Kotlin Multiplatform mobile app · Microservices backend · Contract-first APIs

[![Mobile CI](https://github.com/epr-ds/nutriplan/actions/workflows/mobile.yml/badge.svg)](https://github.com/epr-ds/nutriplan/actions/workflows/mobile.yml)
[![Backend CI](https://github.com/epr-ds/nutriplan/actions/workflows/backend.yml/badge.svg)](https://github.com/epr-ds/nutriplan/actions/workflows/backend.yml)
[![Contracts](https://github.com/epr-ds/nutriplan/actions/workflows/contracts.yml/badge.svg)](https://github.com/epr-ds/nutriplan/actions/workflows/contracts.yml)
[![CodeQL](https://github.com/epr-ds/nutriplan/actions/workflows/codeql.yml/badge.svg)](https://github.com/epr-ds/nutriplan/actions/workflows/codeql.yml)

</div>

---

## What is NutriPlan?

A mobile-first application that combines **AI meal planning**, **nutrition tracking**, and
**multi-channel fulfillment** — dark-kitchen prepared meals, grocery delivery via external
e-commerce providers, or simply saving a digital plan.

Built around four bounded contexts: **Identity**, **Dietary Planning**, **Commerce**, and
**Notification**, plus a dedicated **AI** service.

## Repository layout (monorepo)

```
nutriplan/
├── mobile/        # Kotlin Multiplatform app (shared logic + Compose Android + SwiftUI iOS)
│   ├── shared/        #   Clean-Architecture shared module (domain / data / di)
│   ├── androidApp/    #   Jetpack Compose application
│   └── iosApp/        #   SwiftUI application
├── services/      # Backend microservices
│   ├── identity/      #   Auth, profile, dietary preferences (Postgres)
│   ├── dietary/       #   Meal plans, recipes, nutrition (MongoDB)
│   ├── commerce/      #   Orders, fulfillment, payments (Postgres)
│   ├── notification/  #   Push & events (Redis)
│   └── ai/            #   Recommendations & optimization (Python / FastAPI + LLM)
├── contracts/     # OpenAPI 3.0 specs — the source of truth for every API
├── infra/         # docker-compose, IaC, deployment manifests
└── docs/          # Roadmap, architecture, ADRs
```

> **Why a monorepo?** This is a contract-driven system: a single OpenAPI change can ripple
> into the mobile client and a backend service. A monorepo makes those changes atomic, keeps
> one source of truth for contracts, and unifies tooling/CI. Services remain independently
> deployable via path-filtered pipelines.

## Getting started

### Prerequisites
| Tool | Version | For |
|------|---------|-----|
| JDK | 17+ | Mobile (KMP) build |
| Android Studio | Ladybug+ | Android app |
| Xcode | 15+ (macOS) | iOS app |
| Python | 3.12+ | AI service |
| Docker | 24+ | Local backend stack |
| Node | 20+ | Contract linting (Spectral) |

### Mobile
```bash
cd mobile
./gradlew :androidApp:assembleDebug    # build the Android app
./gradlew :shared:allTests             # run shared module tests
./gradlew detekt                       # static analysis
```
iOS: open `mobile/iosApp` in Xcode once the project is generated (see `mobile/iosApp/README.md`).

### Backend (local stack)
```bash
cd infra
cp .env.example .env
docker compose up -d        # postgres, mongo, redis, ai-service
```

### Contracts
```bash
npx @stoplight/spectral-cli lint "contracts/*.openapi.yaml"
```

## Documentation
- 📍 [Development Roadmap](docs/NutriPlan-Roadmap.md)
- 🏛️ [Architecture & ADRs](docs/architecture/)
- 🤝 [Contributing](CONTRIBUTING.md)
- 🔐 [Security Policy](SECURITY.md)

## License
Proprietary — All Rights Reserved. See [LICENSE](LICENSE).
