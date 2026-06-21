# iOS App (SwiftUI)

The SwiftUI sources live here, but the **Xcode project (`iosApp.xcodeproj`) is intentionally
not committed yet** — it must be generated on a macOS machine with Xcode, which is where iOS
work begins in Phase 0.

## Creating the Xcode project (one-time, on macOS)

1. Open Xcode → **File ▸ New ▸ Project ▸ iOS ▸ App**.
   - Product Name: `iosApp`
   - Interface: **SwiftUI**, Language: **Swift**
   - Save it inside `mobile/iosApp/` so it sits next to this folder.
2. Delete Xcode's generated `ContentView.swift` / `iOSApp.swift` and add the ones already in
   `iosApp/` (`ContentView.swift`, `iOSApp.swift`).
3. Wire in the Kotlin Multiplatform `Shared` framework by adding a **Run Script** build phase
   (before *Compile Sources*):

   ```bash
   cd "$SRCROOT/.."
   ./gradlew :shared:embedAndSignAppleFrameworkForXcode
   ```

   Then set **Framework Search Paths** to `$(SRCROOT)/../shared/build/xcode-frameworks/...`
   (Xcode will surface the exact path after the first Gradle run), and add `Shared.framework`
   to *Frameworks, Libraries, and Embedded Content*.
4. Build & run on a simulator. You should see the greeting from the shared module.

## Why not commit a generated project?

A hand-written `.xcodeproj`/`.pbxproj` is brittle and easily corrupted. Generating it from
Xcode (or later via a tool like XcodeGen / Tuist with a checked-in `project.yml`) is the
reliable approach. Adopting **XcodeGen** is a recommended Phase 0 task so the project becomes
reproducible from a spec file.
