# HRD-701: iOS App Signing + Release Configuration Guide

## Current State
The iOS app (`mobile/iosApp/`) currently has only 3 placeholder Swift files — no Xcode project exists yet. All real UI is in Compose Multiplatform code under `androidApp/screen/`. This guide covers the signing setup needed when the iOS project is created.

---

## Required Setup (Before First Release)

### 1. Apple Developer Program
- Enroll in [Apple Developer Program](https://developer.apple.com/programs/) ($99/year)
- Create App ID: `com.nutriplan.ios` (or whatever bundle identifier is chosen)
- Enable Push Notifications capability if needed

### 2. Keychain Access — Generate / Import Signing Certificates
```bash
# Check existing certificates in keychain
security find-identity -v -p codesigning

# Required certificates:
#   - Apple Development: for local debugging on device
#   - Apple Distribution: for App Store submission
#   - iOS Distribution (if using enterprise)
```

### 3. Provisioning Profiles
Create in [Apple Developer Portal > Certificates, Identifiers & Profiles](https://developer.apple.com/account):
- **Development Profile**: for Xcode debugging on physical devices
- **Distribution Profile** (Ad Hoc or App Store): for release builds

Store profiles securely:
```bash
# Option A: Install via Xcode (recommended for dev machines)
xcodebuild -list -project iosApp.xcodeproj

# Option B: Place in CI keychain (see CI section below)
security import profile.mobileprovision ...
```

### 4. Bundle Identifier & Info.plist
When creating the Xcode project, set:
- **Bundle Identifier**: `com.nutriplan.ios` (must match Apple Developer App ID)
- **Display Name**: NutriPlan
- **Info.plist**: Add required keys:
  - `NSCameraUsageDescription` — for meal photo capture
  - `NSPhotoLibraryUsageDescription` — for saving/exporting plans
  - `NSLocationWhenInUseUsageDescription` — for restaurant/location features

### 5. Push Notifications (APNs) — Entitlements + Capabilities
The iOS push setup (NTF-503) requires the following, configured in Xcode / the Apple Developer Portal:

- **Push Notifications capability**: enable it for the App ID in App Store Connect / Apple Developer Portal.
- **APNs entitlement**: add the `aps-environment` entitlement to the app target — `development` for
  development builds and local debugging, `production` for App Store / TestFlight / release builds.
- **Background modes**: add `remote-notification` to the `UIBackgroundModes` key of the Info.plist so
  background pushes are delivered.

The app side implements this in code: `PushNotificationManager` registers the device through
`UIApplication.registerForRemoteNotifications()`, handles the token handover, and implements the
`UNUserNotificationCenterDelegate` foreground (`willPresent`) and background (`didReceive response`)
paths; taps forward the payload's `deepLink` (NTF-304) through the app-side callback.

---

## CI/CD Setup (GitHub Actions)

### Required Secrets
Add to GitHub repository secrets:
| Secret | Description |
|--------|-------------|
| `IOS_CERTIFICATE` | Base64-encoded `.p12` certificate file |
| `IOS_CERTIFICATE_PASSWORD` | Password for the `.p12` file |
| `IOS_PROVISIONING_PROFILE` | Base64-encoded `.mobileprovision` profile |
| `IOS_KEYCHAIN_PASSWORD` | Temporary keychain password (random) |

### Fastlane (Recommended)
Create `mobile/fastlane/Fastfile`:
```ruby
default_platform(:ios)

platform :ios do
  desc "Build and submit to App Store"
  lane :release do
    match(
      type: "appstore",
      git_url: "https://github.com/epr-ds/nutriplan-ios-signing.git",
      keychain_name: "tmp_build_keychain",
      keychain_password: ENV["IOS_KEYCHAIN_PASSWORD"]
    )

    build_app(
      scheme: "iosApp",
      export_method: "app-store",
      export_options: {
        provisioningProfiles: { "com.nutriplan.ios" => match_profile_name }
      }
    )

    upload_to_app_store(
      skip_metadata: false,
      skip_screenshots: true,
      submit_for_review: true
    )
  end
end
```

### Xcode Project Signing (Manual)
When creating the `.xcodeproj`:
1. Select project → Target → **Signing & Capabilities**
2. Check "Automatically manage signing"
3. Select team: `epr-ds` (or appropriate Apple team)
4. Bundle identifier should auto-populate

---

## Versioning Strategy

### iOS Info.plist Version Keys
| Key | Value Format | Example |
|-----|-------------|---------|
| `CFBundleShortVersionString` | Semantic version (`MAJOR.MINOR.PATCH`) | `"0.1.0"` |
| `CFBundleVersion` (build number) | Incrementing integer | `"1"` |

### CI Build Number Generation
```yaml
# In GitHub Actions workflow:
- name: Set build number
  run: echo "BUILD_NUMBER=$(date +%Y%m%d)-$GITHUB_RUN_NUMBER" >> $GITHUB_ENV
```

---

## Checklist Before First Release
- [ ] Apple Developer Program enrollment confirmed
- [ ] App ID created in Developer Portal
- [ ] Push Notifications capability enabled on the App ID
- [ ] `aps-environment` entitlement configured (development / production)
- [ ] Background modes (`remote-notification`) configured in Info.plist
- [ ] Distribution certificate generated and installed on CI
- [ ] Provisioning profile created for App Store distribution
- [ ] Xcode project with correct bundle identifier
- [ ] Fastlane configured (or manual signing steps documented)
- [ ] GitHub secrets populated (certificate, provisioning profile, passwords)
- [ ] TestFlight account set up for beta testing
- [ ] App Store Connect app record created
