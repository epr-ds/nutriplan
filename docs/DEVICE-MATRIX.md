# Cross-Device / OS-Version Test Matrix (HRD-902)

## Purpose

Define the device and OS version matrix for QA testing. This matrix ensures
NutriPlan works across all supported devices and OS versions.

## Android Matrix

| Device Category | Devices | OS Versions | Min SDK | Target SDK |
|-----------------|---------|-------------|---------|------------|
| Phone (Flagship) | Pixel 8, Pixel 9 | Android 14, Android 15 | 34 | 36 |
| Phone (Mid-range) | Pixel 7a, Samsung Galaxy A54 | Android 13, Android 14 | 33 | 36 |
| Phone (Budget) | Samsung Galaxy A14, Redmi Note 12 | Android 12, Android 13 | 31 | 36 |
| Tablet | Pixel Tablet, Samsung Galaxy Tab S9 | Android 14, Android 15 | 34 | 36 |
| Foldable | Pixel Fold, Samsung Galaxy Z Fold | Android 14, Android 15 | 34 | 36 |

### Screen Densities
- mdpi (160dpi) - Budget phones
- hdpi (240dpi) - Older phones
- xhdpi (320dpi) - Most phones
- xxhdpi (480dpi) - Flagship phones
- xxxhdpi (640dpi) - High-res phones/tablets

### Architectures
- arm64-v8a (primary)
- armeabi-v7a (compatibility)
- x86_64 (emulator)

## iOS Matrix

| Device Category | Devices | OS Versions |
|-----------------|---------|-------------|
| Phone (Flagship) | iPhone 15 Pro, iPhone 15 Pro Max | iOS 17, iOS 18 |
| Phone (Recent) | iPhone 14, iPhone 13 | iOS 16, iOS 17, iOS 18 |
| Phone (Legacy) | iPhone 12, iPhone SE (3rd gen) | iOS 15, iOS 16, iOS 17 |
| Tablet | iPad Air (5th gen), iPad Pro (M2) | iPadOS 17, iPadOS 18 |
| TV | Apple TV 4K (3rd gen) | tvOS 17, tvOS 18 |

### Screen Sizes
- 375x667 (iPhone 8 / SE)
- 390x844 (iPhone 12/13/14)
- 428x926 (iPhone 14/15 Pro Max)
- 768x1024 (iPad)
- 1366x1048 (iPad Pro)

## Testing Priorities

### P0 (Every PR)
- Pixel 7/8 on Android 14
- iPhone 13/14 on iOS 17
- Emulator: Android 14 (API 34)
- Simulator: iOS 17

### P1 (Daily)
- All flagship devices
- All recent OS versions
- Tablet layouts

### P2 (Weekly)
- Budget devices
- Legacy OS versions
- Foldable devices
- Edge cases (low storage, low battery)

## Device Farm Configuration

### Firebase Test Lab
```yaml
android:
  devices:
    - model: Pixel2
      version: 30  # Android 11
      locale: en
      orientation: portrait
    - model: Pixel2
      version: 34  # Android 14
      locale: en
      orientation: portrait
    - model: GalaxyS20
      version: 33  # Android 13
      locale: es
      orientation: portrait
  localization:
    - en
    - es
ios:
  devices:
    - model: iPhone 13
      version: 17.0
    - model: iPhone 12
      version: 16.0
    - model: iPad Air (5th gen)
      version: 17.0
  localization:
    - en-US
    - es-MX
```

### BrowserStack / Sauce Labs
```yaml
browsers:
  - browser: Chrome
    version: latest
    platform: Windows 11
  - browser: Safari
    version: latest
    platform: macOS Sonoma
  - browser: Firefox
    version: latest
    platform: Windows 11
```

## Accessibility Testing Devices

| Device | Feature | Test |
|--------|---------|------|
| Pixel 8 | TalkBack | Screen reader navigation |
| iPhone 15 | VoiceOver | Screen reader navigation |
| Pixel 8 | Magnification | 200% font scale |
| iPhone 15 | Dynamic Type | Largest font size |
| All | Contrast | WCAG AA contrast ratios |

## References

- [HRD-902: Cross-device / OS-version matrix](https://github.com/epr-ds/nutriplan/issues/348)
- [HRD-301: WCAG 2.1 AA audit](https://github.com/epr-ds/nutriplan/issues/306)
- [HRD-302/303: Accessibility fixes](https://github.com/epr-ds/nutriplan/issues/319)
- [HRD-304: Dynamic type / contrast pass](https://github.com/epr-ds/nutriplan/issues/337)
