++ b/mobile/shared/src/androidMain/kotlin/com/nutriplan/shared/ui/theme/Theme.kt
package com.nutriplan.shared.ui.theme

import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalInspectionMode

/**
 * Get the current platform name for debugging/logging.
 */
@Composable
fun getPlatformName(): String = if (LocalInspectionMode.current) {
    "Preview"
} else {
    "Unknown"
}
