package com.nutriplan.android.a11y

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.ui.theme.NutriPlanTheme
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * WCAG 1.4.3 Contrast Minimum (AA ≥ 4.5:1 for normal text).
 *
 * Verifies that every text color used on a surface has sufficient contrast in both light and dark
 * themes. Runs on the JVM via Robolectric.
 */
@RunWith(AndroidJUnit4::class)
@Config(sdk = [34], application = TestApplication::class)
class ColorContrastTest {

    @get:Rule
    val compose = createComposeRule()

    private fun luminance(color: Color): Float {
        val rgb = listOf(color.componentRed, color.componentGreen, color.componentBlue)
            .map { it / 255f }
            .map { if (it <= 0.03929f) it / 12.92f else ((it + 0.055f) / 1.055f) pow 2.4f }
        return 0.2126f * rgb[0] + 0.7152f * rgb[1] + 0.0722f * rgb[2]
    }

    private fun contrast(fg: Color, bg: Color): Float {
        val l1 = luminance(fg)
        val l2 = luminance(bg)
        return (max(l1, l2) + 0.05f) / (min(l1, l2) + 0.05f)
    }

    private fun assertContrastAtLeast(fg: Color, bg: Color, minimum: Float) {
        val actual = contrast(fg, bg)
        assert(actual >= minimum, "Contrast $actual:1 < $minimum:1 for fg=$fg bg=$bg")
    }

    private fun renderTheme(dark: Boolean) {
        compose.setContent {
            NutriPlanTheme(darkTheme = dark) {
                // Empty content — just need the theme to be applied.
            }
        }
    }

    @Test
    fun `onSurface text on surface background passes AA in light theme`() {
        renderTheme(dark = false)
        val scheme = MaterialTheme.colorScheme
        assertContrastAtLeast(scheme.onSurface, scheme.surface, 4.5f)
    }

    @Test
    fun `onSurfaceVariant text on surface background passes AA in light theme`() {
        renderTheme(dark = false)
        val scheme = MaterialTheme.colorScheme
        assertContrastAtLeast(scheme.onSurfaceVariant, scheme.surface, 4.5f)
    }

    @Test
    fun `onSurfaceVariant text on surfaceVariant background passes AA in light theme`() {
        renderTheme(dark = false)
        val scheme = MaterialTheme.colorScheme
        assertContrastAtLeast(scheme.onSurfaceVariant, scheme.surfaceVariant, 4.5f)
    }

    @Test
    fun `onSurfaceVariant text on surfaceVariant background passes AA in dark theme`() {
        renderTheme(dark = true)
        val scheme = MaterialTheme.colorScheme
        assertContrastAtLeast(scheme.onSurfaceVariant, scheme.surfaceVariant, 4.5f)
    }

    @Test
    fun `onSurface text on surface background passes AA in dark theme`() {
        renderTheme(dark = true)
        val scheme = MaterialTheme.colorScheme
        assertContrastAtLeast(scheme.onSurface, scheme.surface, 4.5f)
    }
}
