package com.nutriplan.shared.onboarding

import kotlin.test.Test
import kotlin.test.assertEquals

class MacroCalculatorTest {

    @Test
    fun `clamps calories into the contract range`() {
        assertEquals(MacroCalculator.MIN_CALORIES, MacroCalculator.clampCalories(1000))
        assertEquals(MacroCalculator.MAX_CALORIES, MacroCalculator.clampCalories(9000))
        assertEquals(1800, MacroCalculator.clampCalories(1800))
    }

    @Test
    fun `splits a 2000 kcal target into balanced macros`() {
        val macros = MacroCalculator.defaultMacroTargets(2000)

        assertEquals(150, macros.proteinGrams)
        assertEquals(200, macros.carbsGrams)
        assertEquals(66, macros.fatGrams)
    }

    @Test
    fun `clamps before computing macros`() {
        val macros = MacroCalculator.defaultMacroTargets(1000)

        assertEquals(MacroCalculator.defaultMacroTargets(MacroCalculator.MIN_CALORIES), macros)
    }
}
