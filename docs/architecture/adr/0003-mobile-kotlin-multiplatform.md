# 3. Kotlin Multiplatform for mobile

- Status: Accepted
- Date: 2026-06-20

## Context

The product targets both Android and iOS. We want to maximize code reuse for domain and data
logic while keeping a native-quality UI on each platform.

## Decision

We will build the mobile app with **Kotlin Multiplatform (KMP)**:

- A shared module holds the **domain**, **data**, and **DI** layers (Kotlin, Ktor, coroutines,
  serialization).
- **Android UI** is built with **Jetpack Compose**.
- **iOS UI** is built with **SwiftUI**, consuming the shared module as a framework.

## Consequences

- Business and networking logic is written once and shared.
- UI stays idiomatic and native on each platform (no shared-UI abstraction tax).
- iOS builds require macOS + Xcode; the iOS app's Xcode project is generated on macOS
  (XcodeGen adoption is a follow-up task).
- Team needs Kotlin proficiency; iOS engineers interact with a generated Kotlin framework.
