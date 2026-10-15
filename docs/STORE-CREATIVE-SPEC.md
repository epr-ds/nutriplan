# HRD-1003 — Store Creative Specification

> As a shopper, the store creative sells the app.

## Screenshots

### Google Play Store (Android)

| Device Type | Resolution | Count Required | Count Recommended |
|-------------|-----------|----------------|-------------------|
| Phone (7") | 1600×3200 px | 2–5 | 5 |
| 7" Tablet | 1920×1200 px | 2–5 | 2 |
| 10" Tablet | 2560×1600 px | 2–5 | 2 |
| Foldable | 2268×1932 px | 2–5 | 2 |
| Desktop | 3840×1080 px | 2–5 | 2 |

**Minimum**: 2 screenshots (any device type)
**Recommended**: 5 screenshots (phone) + 2 each tablet

### Apple App Store (iOS)

| Device Type | Resolution |
|-------------|-----------|
| iPhone 6.7" | 1290×2796 px |
| iPhone 6.5" | 1170×2532 px |
| iPhone 5.4" | 1080×2340 px |
| iPad 12.9" | 2048×2732 px |
| iPad 11" | 1640×2360 px |

**Minimum**: 1 screenshot (any device type)
**Recommended**: 5 screenshots (iPhone) + 2 each iPad

---

## Screenshot Content Plan

### Primary Screenshots (Phone — 5 images)

| # | Screen | Purpose | Language |
|---|--------|---------|----------|
| 1 | Onboarding (dietary preferences) | Show personalization | en |
| 2 | Onboarding (allergy selection) | Show safety features | en |
| 3 | Home (meal plan view) | Show core value prop | en |
| 4 | Checkout (order summary) | Show commerce flow | en |
| 5 | Profile (settings) | Show customization | en |

### Spanish Screenshots (Phone — 5 images)

| # | Screen | Purpose | Language |
|---|--------|---------|----------|
| 1 | Onboarding (preferencias dietéticas) | Mostrar personalización | es |
| 2 | Onboarding (selección de alergias) | Mostrar funciones de seguridad | es |
| 3 | Inicio (vista del plan de comidas) | Mostrar propuesta de valor | es |
| 4 | Checkout (resumen del pedido) | Mostrar flujo de compra | es |
| 5 | Perfil (configuración) | Mostrar personalización | es |

### Tablet Screenshots (2 each)

| # | Screen | Purpose |
|---|--------|---------|
| 1 | Home (meal plan grid) | Show multi-column layout |
| 2 | Profile (settings panel) | Show expanded settings |

---

## Preview Video

| Spec | Value |
|------|-------|
| Duration | 30 seconds (max) |
| Resolution | 1920×1080 px (min) |
| Format | MP4 or MOV |
| File size | 100 MB (max) |
| Aspect ratio | 16:9 |

**Content plan**:
1. 0–5s: App logo + tagline
2. 5–15s: Onboarding flow (dietary preferences → allergies)
3. 15–25s: Meal plan creation → checkout flow
4. 25–30s: CTA ("Download now")

---

## Feature Graphic (Google Play)

| Spec | Value |
|------|-------|
| Resolution | 1024×500 px |
| Format | PNG or JPEG (256-color min) |
| File size | 1 MB (max) |
| Safe area | Center 830×500 px (edges may be cropped) |

---

## App Icon

| Spec | Value |
|------|-------|
| Resolution | 512×512 px |
| Format | PNG |
| Background | Solid color (no transparency) |
| Border radius | 0 (store applies its own) |

---

## Store Listing Copy

### Short Description (80 chars max)
- **en**: "Personalized meal plans for your dietary needs"
- **es**: "Planes de comidas personalizados para tus necesidades"

### Full Description (8000 chars max)
- **en**: See `docs/STORE-LISTING-COPY.md` (to be created)
- **es**: See `docs/STORE-LISTING-COPY-ES.md` (to be created)

---

## Validation Checklist

### Before Submission

- [ ] All screenshots meet store resolution specs
- [ ] Screenshots show real app UI (no mockups)
- [ ] Screenshots are in focus (no blur, no motion artifacts)
- [ ] No text overlaps or cut-off in screenshots
- [ ] Screenshots are in correct language (en/es)
- [ ] Preview video plays correctly on all devices
- [ ] Feature graphic fits within safe area
- [ ] App icon has solid background, no transparency
- [ ] Store listing copy reviewed by legal (ToS/privacy compliant)
- [ ] Store listing copy reviewed by design (brand consistency)

### CI Validation (automated)

- [ ] Script to validate screenshot dimensions
- [ ] Script to validate feature graphic safe area
- [ ] Script to validate app icon format

---

## References

- [Google Play Console — Screenshots](https://support.google.com/googleplay/android-developer/answer/9323626)
- [App Store Connect — App Screenshots](https://developer.apple.com/documentation/app-store-connect/screenshots)
- [Material Design — App Icon](https://m3.material.io/styles/iconography/general-guidelines/app-icon)
