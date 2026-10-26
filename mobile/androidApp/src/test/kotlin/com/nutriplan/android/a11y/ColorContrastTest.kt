package com.nutriplan.android.a11y

import androidx.compose.material3.MaterialTheme
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.ui.theme.NutriPlanTheme
import org.junit.Assert.assertTrue
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
        fun channel(component: Float): Float {
            val value = component / 255f
            return if (value <= 0.03929f) {
                value / 12.92f
            } else {
                Math.pow(((value + 0.055f) / 1.055f).toDouble(), 2.4).toFloat()
            }
        }
        return 0.2126f * channel(color.red) + 0.7152f * channel(color.green) + 0.0722f * channel(color.blue)
    }

    private fun contrast(fg: Color, bg: Color): Float {
        val l1 = luminance(fg)
        val l2 = luminance(bg)
        return (maxOf(l1, l2) + 0.05f) / (minOf(l1, l2) + 0.05f)
    }

    @Test
    fun `onSurface text on surface background passes AA in light theme`() {
        compose.setContent {
            val scheme = MaterialTheme.colorScheme
            assertTrue(contrast(scheme.onSurface, scheme.surface) >= 4.5f, "AA contrast failed")
        }
    }

    @Test
    fun `onSurfaceVariant text on surface background passes AA in light theme`() {
        compose.setContent {
            val scheme = MaterialTheme.colorScheme
            assertTrue(contrast(scheme.onSurfaceVariant, scheme.surface) >= 4.5f, "AA contrast failed")
        }
    }

    @Test
    fun `onSurfaceVariant text on surfaceVariant background passes AA in light theme`() {
        compose.setContent {
            val scheme = MaterialTheme.colorScheme
            assertTrue(contrast(scheme.onSurfaceVariant, scheme.surfaceVariant) >= 4.5f, "AA contrast failed")
        }
    }

    @Test
    fun `onSurfaceVariant text on surfaceVariant background passes AA in dark theme`() {
        compose.setContent {
            val scheme = MaterialTheme.colorScheme
            assertTrue(contrast(scheme.onSurfaceVariant, scheme.surfaceVariant) >= 4.5f, "AA contrast failed")
        }
    }

    @Test
    fun `onSurface text on surface background passes AA in dark theme`() {
        compose.setContent {
            val scheme = MaterialTheme.colorScheme
            assertTrue(contrast(scheme.onSurface, scheme.surface) >= 4.5f, "AA contrast failed")
        }
    }
}
