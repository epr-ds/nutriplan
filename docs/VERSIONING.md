# NutriPlan Versioning Strategy (HRD-701)

## Android (`mobile/androidApp/build.gradle.kts`)

| Field | Format | Current | Notes |
|-------|--------|---------|-------|
| `versionCode` | Incrementing integer | `1` | Bump per release. Use `YYYYMMDDNN` format (e.g., `2026101301`). |
| `versionName` | Semantic version (`MAJOR.MINOR.PATCH`) | `"0.1.0"` | Follows [semver](https://semver.org/). Bump per store release. |

### Release Flow
1. Merge to `release/*` branch → triggers GA release gate (workflow_dispatch)
2. CI builds signed APK with Play App Signing upload key
3. Upload to Google Play Console → internal testing track first
4. After validation, promote to production

## iOS (`mobile/iosApp/Info.plist`)

| Field | Format | Current | Notes |
|-------|--------|---------|-------|
| `CFBundleShortVersionString` | Semantic version | `"0.1.0"` (pending) | Matches Android `versionName`. Keep in sync. |
| `CFBundleVersion` | Incrementing integer | `1` (pending) | Bump per TestFlight/App Store submission. |

### Release Flow
1. Merge to `release/*` branch → triggers iOS build via Fastlane or manual Xcode archive
2. Archive → upload to App Store Connect via Transporter / Xcode
3. Submit for review → TestFlight first, then production

## Sync Strategy
- **Android and iOS versionName must stay in sync** at all times.
- Use a single source of truth: `mobile/shared/src/commonMain/kotlin/com/nutriplan/shared/Version.kt`:
  ```kotlin
  object Version {
      const val MAJOR = 0
      const val MINOR = 1
      const val PATCH = 0
      const val NAME = "$MAJOR.$MINOR.$PATCH"
  }
  ```
- Android build.gradle reads from this; iOS Info.plist updated via CI script.

## Pre-GA Version Target
- **Target**: `0.1.0` for GA launch (P6)
- Post-GA: bump to `1.0.0` when feature-complete and stable.
