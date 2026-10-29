package com.nutriplan.android.ui.theme

import androidx.compose.ui.text.TextStyle
import org.junit.Assert.assertTrue
import org.junit.Test

/** HRD-1001: the design token typography scale keeps line heights within the documented ratio. */
class NutriPlanTypographyTest {

    private fun lineHeightRatio(style: TextStyle): Float {
        val size = style.fontSize.value
        return style.lineHeight.value / size
    }

    @Test
    fun `line heights stay within the design ratio`() {
        val styles = listOf(
            NutriPlanTypography.displayLarge,
            NutriPlanTypography.displayMedium,
            NutriPlanTypography.displaySmall,
            NutriPlanTypography.headlineLarge,
            NutriPlanTypography.headlineMedium,
            NutriPlanTypography.headlineSmall,
            NutriPlanTypography.titleLarge,
            NutriPlanTypography.titleMedium,
            NutriPlanTypography.titleSmall,
            NutriPlanTypography.bodyLarge,
            NutriPlanTypography.bodyMedium,
            NutriPlanTypography.bodySmall,
            NutriPlanTypography.labelLarge,
            NutriPlanTypography.labelMedium,
            NutriPlanTypography.labelSmall,
        )
        styles.forEach { style ->
            val ratio = lineHeightRatio(style)
            assertTrue(
                "line height ratio ${ratio} out of bounds for font size ${style.fontSize.value}",
                ratio >= 1.25f && ratio <= 1.5f,
            )
        }
    }
}