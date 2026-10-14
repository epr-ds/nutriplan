# Fastlane Configuration — NutriPlan Beta Distribution

## Setup Requirements

### Android (Play Internal Testing)

1. **Google Play Developer Account**
   - Create a developer account at https://play.google.com/console
   - Create an app entry for `com.nutriplan.android`

2. **Service Account JSON Key**
   - Go to Settings → Service Accounts in Play Console
   - Generate a new private key (JSON)
   - Add the JSON content as GitHub secret: `PLAY_STORE_JSON_KEY`

3. **Create Internal Testing Track**
   - In Play Console, create an "Internal testing" track
   - Add tester email addresses to the tester list

### iOS (TestFlight)

1. **Apple Developer Account**
   - Enroll in Apple Developer Program at https://developer.apple.com/program/
   - Create an App ID for `com.nutriplan.ios`

2. **GitHub Secrets Required**
   ```
   APPLE_ID          = your@appleid.com
   APPLE_USERNAME    = your@appleid.com
   APP_APPLE_PASSWORD = @app-specific-password (NOT your Apple ID password)
   FASTLANE_ITC_APP_ID = your iTunes Connect app ID (numeric)
   ```

3. **Xcode Workspace**
   - Create workspace: `cd mobile/iosApp && xcodebuild -create-xcworkspace -name NutriPlan`
   - Add scheme for the iOS target

### Alternative: Firebase App Distribution

For both platforms, you can use Firebase as an alternative distribution channel:

1. Create a Firebase project at https://console.firebase.google.com
2. Register `com.nutriplan.android` and your iOS bundle ID
3. Generate a service account key or auth token
4. Add to GitHub secrets: `FIREBASE_TOKEN` (for CLI) or `FIREBASE_SERVICE_ACCOUNT`

## Tester Groups Setup

### Play Store Internal Testing
1. Go to Play Console → Your App → Testing → Internal testing
2. Add tester emails under "Tester management"
3. Share the internal testing link with testers

### Firebase App Distribution
```bash
# Install Firebase CLI
npm install -g firebase-tools

# Login
firebase login

# Create group (requires firebase project setup)
firebase appdistribution:distribution groups create beta-testers \
  --app YOUR_FIREBASE_APP_ID \
  --emails tester1@example.com,tester2@example.com
```

### TestFlight Groups
1. Go to App Store Connect → Your App → TestFlight
2. Create a "Beta" group under "Groups"
3. Add tester Apple IDs (must have Apple ID accounts)

## Running Locally

```bash
# Android beta to Play Internal
cd mobile/fastlane
bundle install
fastlane beta

# Android beta to Firebase
fastlane firebase_beta

# iOS beta to TestFlight (macOS required)
fastlane beta

# iOS beta to Firebase
fastlane firebase_beta_ios
```

## CI/CD Usage

Trigger the beta workflow manually from GitHub Actions:

1. Go to Actions → Mobile Beta Distribution
2. Click "Run workflow"
3. Select platform (android/ios/both) and track (internal/firebase)

Or via CLI:
```bash
gh workflow run beta.yml -f platform=android -f track=internal
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `No such file or directory` on fastlane install | Run `gem install fastlane` first |
| Play Console auth failed | Verify `PLAY_STORE_JSON_KEY` secret is valid JSON |
| TestFlight upload fails | Check App Password (not Apple ID password) |
| Firebase distribution fails | Verify token has appdistribution.uploader role |

## Related Issues

- HRD-601: TestFlight + Play internal beta pipeline + tester groups
- HRD-603: Closed beta launch + feedback intake
- HRD-905: Bug bash + triage before GA
