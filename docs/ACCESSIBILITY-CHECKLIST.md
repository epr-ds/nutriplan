# HRD-305 — Accessibility Manual Testing Checklist

> As the team, a11y doesn't regress after GA.

## Automated Checks (CI)

### Compose Semantics / Accessibility Checks (JVM)
- **Location**: `mobile/androidApp/src/test/kotlin/com/nutriplan/android/a11y/`
  (`AuthAccessibilityTest`, `OnboardingAccessibilityTest`, `A11yMatchers`)
- **Run**: `./gradlew :androidApp:testDebugUnitTest`
- **CI Job**: `android-a11y` in `.github/workflows/mobile.yml`
- **Critical checks**:
  1. Missing content description / label on interactive elements
  2. Touch target < 48x48dp (WCAG 2.5.5)
  3. Errors associated with their field and announced (live region)
  4. Screen titles exposed as headings

> These run on the JVM with Robolectric (no emulator), so they are a fast, deterministic guard.
> Deep contrast/traversal checks from the Accessibility Test Framework (ATF) require an API 34+
> device (`enableAccessibilityChecks`) and are not covered here.

### Android Lint (accessibility rules)
- **Run**: `./gradlew :androidApp:lintDebug`
- **CI Job**: `android-a11y` in `.github/workflows/mobile.yml` (`ANDROID_LINT_COMPLETE=1`)

### Detekt A11y Rules
- **Location**: `mobile/config/detekt/detekt.yml`
- **Run**: `./gradlew detekt`
- **CI Job**: `android` in `.github/workflows/mobile.yml`

---

## Manual Testing Checklist

### 1. Screen Reader (TalkBack) Testing

#### Onboarding
- [ ] All page dots are announced with content description
- [ ] "Skip" button is announced
- [ ] "Get started" button is announced
- [ ] Each onboarding page title and description is read aloud
- [ ] Swipe navigation is announced

#### Login
- [ ] Email field label is announced
- [ ] Password field label is announced
- [ ] "Sign in" button is announced
- [ ] "Forgot password?" link is announced
- [ ] Error messages are announced when they appear

#### Home
- [ ] Meal plan cards are announced with title, date, and calories
- [ ] "View details" button is announced
- [ ] Navigation drawer (if any) is accessible

#### Checkout
- [ ] Order summary items are announced
- [ ] Price totals are announced
- [ ] "Place order" button is announced
- [ ] Terms text is announced

#### Profile
- [ ] User info is announced
- [ ] Menu items are announced
- [ ] "Sign out" button is announced

### 2. Large Font / Dynamic Type Testing

**Steps**:
1. Device Settings → Accessibility → Text and display → Font size → Max
2. Device Settings → Accessibility → Text and display → Magnification → Max
3. Repeat each screen test above

**Expected**:
- [ ] No text clipping or truncation on any screen
- [ ] Layout reflows gracefully
- [ ] All content remains accessible
- [ ] Buttons remain tappable

### 3. Color Contrast Testing

**Tools**: Android Studio Layout Inspector, Accessibility Scanner app

**Check**:
- [ ] All text meets WCAG AA 4.5:1 (normal text) or 3:1 (large text)
- [ ] All interactive elements meet 3:1 contrast against background
- [ ] Color is not the sole indicator of state (use icons/text too)
- [ ] Dark mode tested on all screens

### 4. Touch Target Testing

**Steps**:
1. Enable "Show taps" in Developer Options
2. Tap every interactive element

**Expected**:
- [ ] All interactive elements have ≥ 48x48dp touch target
- [ ] No accidental taps on adjacent elements
- [ ] Grouped small controls have adequate spacing

### 5. Keyboard Navigation (Hardware Keyboard)

**Steps**:
1. Connect hardware keyboard or use USB OTG keyboard
2. Navigate entire app using Tab and Enter

**Expected**:
- [ ] Focus indicator visible on all interactive elements
- [ ] Focus order matches visual order
- [ ] All functionality accessible via keyboard

### 6. Gesture Navigation

**Steps**:
1. Enable gesture navigation in device settings
2. Test all swipe-based interactions

**Expected**:
- [ ] No gesture conflicts with system gestures
- [ ] Alternative tap targets available for all swipes
- [ ] Swipe distance is reasonable

---

## CI Integration

### Adding to CI Pipeline

The `android-a11y` job in `.github/workflows/mobile.yml` runs:

```yaml
android-a11y:
  name: Android accessibility checks
  runs-on: ubuntu-latest
  defaults:
    run:
      working-directory: mobile
  steps:
    - uses: actions/checkout@v7
    - uses: actions/setup-java@v6
      with:
        distribution: temurin
        java-version: '17'
    - uses: gradle/actions/setup-gradle@v6
    - name: Compose semantics/a11y checks (JVM, Robolectric)
      run: ./gradlew :androidApp:testDebugUnitTest --stacktrace
    - name: Android Lint (accessibility rules)
      run: ./gradlew :androidApp:lintDebug --stacktrace
      env:
        ANDROID_LINT_COMPLETE: '1'
```

### Failing CI on Critical Regressions

Critical a11y issues that MUST fail CI:
1. **Missing content description** — Screen readers cannot announce the element
2. **Touch target < 48dp** — Users cannot reliably tap the element
3. **Unreachable semantics node** — Element is invisible to assistive tech
4. **Empty text without alternative** — Content is lost to screen readers

### Manual Checklist Storage

This file (`docs/ACCESSIBILITY-CHECKLIST.md`) is the source of truth for manual a11y testing.
Update it whenever new screens or components are added.

---

## References

- [WCAG 2.1 AA Guidelines](https://www.w3.org/WAI/WCAG21/quickref/)
- [Material Design Accessibility](https://m3.material.io/styles/accessibility/plot)
- [Compose Accessibility Testing](https://developer.android.com/jetpack/compose/testing#a11y)
- [Android Accessibility Scanner](https://developer.android.com/studio/debug/check-infra#accessibility-scanner)
