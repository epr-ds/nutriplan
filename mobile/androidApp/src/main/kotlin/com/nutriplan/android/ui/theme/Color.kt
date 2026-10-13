package com.nutriplan.android.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

/**
 * NutriPlan light color palette.
 */
private val LightColorScheme = lightColorScheme(
    primary = Color(0xFF2E7D32),       // Green 800
    onPrimary = Color(0xFFFFFFFF),
    primaryContainer = Color(0xFFA5D6A7),
    secondary = Color(0xFF006978),      // Teal 800
    onSecondary = Color(0xFFFFFFFF),
    secondaryContainer = Color(0xFF80CBC4),
    tertiary = Color(0xFFF57C00),       // Orange 800
    onTertiary = Color(0xFFFFFFFF),
    tertiaryContainer = Color(0xFFFFCC80),
    background = Color(0xFFF9F9F9),
    onBackground = Color(0xFF1B1B1B),
    surface = Color(0xFFFFFFFF),
    onSurface = Color(0xFF1B1B1B),
    surfaceVariant = Color(0xFFF5F5F5),
    error = Color(0xFFD32F2F),
    onError = Color(0xFFFFFFFF),
)

/**
 * NutriPlan dark color palette.
 */
private val DarkColorScheme = darkColorScheme(
    primary = Color(0xFF81C784),        // Green 400
    onPrimary = Color(0xFF000000),
    primaryContainer = Color(0xFF2E7D32),
    secondary = Color(0xFF4DB6AC),      // Teal 400
    onSecondary = Color(0xFF000000),
    secondaryContainer = Color(0xFF006978),
    tertiary = Color(0xFFFFB74D),       // Orange 400
    onTertiary = Color(0xFF000000),
    tertiaryContainer = Color(0xFFE65100),
    background = Color(0xFF121212),
    onBackground = Color(0xFFE0E0E0),
    surface = Color(0xFF1E1E1E),
    onSurface = Color(0xFFE0E0E0),
    surfaceVariant = Color(0xFF2C2C2C),
    error = Color(0xFFEF5350),
    onError = Color(0xFF000000),
)

/**
 * Apply the NutriPlan theme.
 *
 * Uses dark mode if the system is in dark theme.
 */
@Composable
fun NutriPlanTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    val colorScheme = if (darkTheme) DarkColorScheme else LightColorScheme

    MaterialTheme(
        colorScheme = colorScheme,
        typography = NutriPlanTypography,
        content = content,
    )
}
