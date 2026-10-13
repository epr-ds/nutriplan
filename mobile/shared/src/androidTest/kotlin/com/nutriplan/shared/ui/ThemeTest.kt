++ b/mobile/shared/src/androidTest/kotlin/com/nutriplan/shared/ui/ThemeTest.kt
package com.nutriplan.shared.ui.theme

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull

class ThemeTest {

    @Test
    fun `primary color is defined`() {
        val color = NutriPlanTheme.colors.primary
        assertNotNull(color)
    }

    @Test
    fun `onPrimary color is defined`() {
        val color = NutriPlanTheme.colors.onPrimary
        assertNotNull(color)
    }

    @Test
    fun `onSurface color is defined`() {
        val color = NutriPlanTheme.colors.onSurface
        assertNotNull(color)
    }

    @Test
    fun `surface color is defined`() {
        val color = NutriPlanTheme.colors.surface
        assertNotNull(color)
    }

    @Test
    fun `surfaceVariant color is defined`() {
        val color = NutriPlanTheme.colors.surfaceVariant
        assertNotNull(color)
    }

    @Test
    fun `error color is defined`() {
        val color = NutriPlanTheme.colors.error
        assertNotNull(color)
    }

    @Test
    fun `typography headlineLarge is defined`() {
        val typography = NutriPlanTheme.typography.headlineLarge
        assertNotNull(typography)
    }

    @Test
    fun `typography titleMedium is defined`() {
        val typography = NutriPlanTheme.typography.titleMedium
        assertNotNull(typography)
    }

    @Test
    fun `typography bodyLarge is defined`() {
        val typography = NutriPlanTheme.typography.bodyLarge
        assertNotNull(typography)
    }

    @Test
    fun `typography bodyMedium is defined`() {
        val typography = NutriPlanTheme.typography.bodyMedium
        assertNotNull(typography)
    }

    @Test
    fun `typography bodySmall is defined`() {
        val typography = NutriPlanTheme.typography.bodySmall
        assertNotNull(typography)
    }
}
