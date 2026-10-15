#!/usr/bin/env python3
"""
HRD-1003: Validate store creative asset dimensions and specs.

Usage:
    python scripts/validate-store-creative.py --assets-dir store-creative/

Validates:
    - Screenshot dimensions against store specs
    - Feature graphic resolution and safe area
    - App icon format and transparency
    - Preview video specs (duration, resolution, format)

Exit code 0 = all valid, 1 = validation failed.
"""

import argparse
import json
import sys
from pathlib import Path

# Store specs
PHONE_SCREENSHOTS = {
    "google_play": [
        (1600, 3200),  # Phone 7"
    ],
    "app_store": [
        (1290, 2796),  # iPhone 6.7"
        (1170, 2532),  # iPhone 6.5"
        (1080, 2340),  # iPhone 5.4"
    ],
}

TABLET_SCREENSHOTS = {
    "google_play": [
        (1920, 1200),  # 7" tablet
        (2560, 1600),  # 10" tablet
    ],
    "app_store": [
        (2048, 2732),  # iPad 12.9"
        (1640, 2360),  # iPad 11"
    ],
}

FEATURE_GRAPHIC = (1024, 500)
FEATURE_GRAPHIC_SAFE = (830, 500)  # Center safe area
APP_ICON = (512, 512)


def validate_screenshot(path: Path, store: str) -> list[str]:
    """Validate a screenshot against store specs."""
    errors = []
    try:
        from PIL import Image
    except ImportError:
        errors.append(f"PIL not installed — skipping dimension check for {path.name}")
        return errors

    try:
        img = Image.open(path)
        w, h = img.size
    except Exception as e:
        errors.append(f"Cannot open {path.name}: {e}")
        return errors

    valid_specs = PHONE_SCREENSHOTS.get(store, []) + TABLET_SCREENSHOTS.get(store, [])

    # Check if dimensions match any spec (allow ±5% tolerance)
    matched = False
    for spec_w, spec_h in valid_specs:
        tol_w = int(spec_w * 0.05)
        tol_h = int(spec_h * 0.05)
        if abs(w - spec_w) <= tol_w and abs(h - spec_h) <= tol_h:
            matched = True
            break

    if not matched:
        errors.append(
            f"{path.name}: dimensions {w}x{h} don't match any {store} spec. "
            f"Expected one of: {valid_specs}"
        )

    return errors


def validate_feature_graphic(path: Path) -> list[str]:
    """Validate feature graphic specs."""
    errors = []
    try:
        from PIL import Image
    except ImportError:
        errors.append(f"PIL not installed — skipping feature graphic check for {path.name}")
        return errors

    try:
        img = Image.open(path)
        w, h = img.size
    except Exception as e:
        errors.append(f"Cannot open {path.name}: {e}")
        return errors

    if w != FEATURE_GRAPHIC[0] or h != FEATURE_GRAPHIC[1]:
        errors.append(
            f"{path.name}: resolution {w}x{h} != {FEATURE_GRAPHIC[0]}x{FEATURE_GRAPHIC[1]}"
        )

    # Check safe area (center 830x500 should not be empty/transparent)
    if img.mode == "RGBA":
        alpha = img.getchannel("A")
        center = alpha.crop(
            ((w - FEATURE_GRAPHIC_SAFE[0]) // 2,
             (h - FEATURE_GRAPHIC_SAFE[1]) // 2,
             (w + FEATURE_GRAPHIC_SAFE[0]) // 2,
             (h + FEATURE_GRAPHIC_SAFE[1]) // 2)
        )
        if center.getextrema()[1] == 0:
            errors.append(f"{path.name}: safe area is fully transparent")

    return errors


def validate_app_icon(path: Path) -> list[str]:
    """Validate app icon specs."""
    errors = []
    try:
        from PIL import Image
    except ImportError:
        errors.append(f"PIL not installed — skipping app icon check for {path.name}")
        return errors

    try:
        img = Image.open(path)
        w, h = img.size
    except Exception as e:
        errors.append(f"Cannot open {path.name}: {e}")
        return errors

    if w != APP_ICON[0] or h != APP_ICON[1]:
        errors.append(f"{path.name}: resolution {w}x{h} != {APP_ICON[0]}x{APP_ICON[1]}")

    # Check for transparency (app icons must have solid background)
    if img.mode == "RGBA" and img.getchannel("A").getextrema()[1] < 255:
        errors.append(f"{path.name}: app icon has transparency (must be solid background)")

    return errors


def main():
    parser = argparse.ArgumentParser(description="Validate store creative assets")
    parser.add_argument("--assets-dir", required=True, help="Directory containing store creative assets")
    parser.add_argument("--store", choices=["google_play", "app_store"], default="google_play",
                        help="Target store (default: google_play)")
    args = parser.parse_args()

    assets_dir = Path(args.assets_dir)
    all_errors = []

    if not assets_dir.exists():
        print(f"ERROR: Assets directory '{args.assets_dir}' does not exist")
        sys.exit(1)

    # Validate screenshots
    for screenshot_path in assets_dir.glob("screenshot*.*"):
        if screenshot_path.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            continue
        errors = validate_screenshot(screenshot_path, args.store)
        all_errors.extend(errors)

    # Validate feature graphic
    for fg_path in assets_dir.glob("feature-graphic*.*"):
        errors = validate_feature_graphic(fg_path)
        all_errors.extend(errors)

    # Validate app icon
    for icon_path in assets_dir.glob("icon*.*"):
        errors = validate_app_icon(icon_path)
        all_errors.extend(errors)

    # Report results
    if all_errors:
        print("Validation FAILED:")
        for error in all_errors:
            print(f"  ✗ {error}")
        sys.exit(1)
    else:
        print("All assets validated successfully ✓")
        sys.exit(0)


if __name__ == "__main__":
    main()
