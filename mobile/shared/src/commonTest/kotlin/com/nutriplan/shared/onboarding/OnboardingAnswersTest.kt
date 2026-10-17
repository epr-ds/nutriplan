package com.nutriplan.shared.onboarding

import com.nutriplan.shared.data.model.DietaryMacroTargets
import com.nutriplan.shared.data.model.DietaryPreferences
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

class OnboardingAnswersTest {

    @Test
    fun `from maps an existing profile's preferences`() {
        val preferences = DietaryPreferences(
            dietType = "vegan",
            allergies = listOf("peanuts"),
            dailyCalorieTarget = 1800,
            macroTargets = DietaryMacroTargets(proteinGrams = 135, carbsGrams = 180, fatGrams = 60),
            excludedIngredients = listOf("mushrooms"),
            cuisinePreferences = listOf("asian"),
            appetiteSatisfactionLevel = 4,
        )

        val answers = OnboardingAnswers.from(preferences)

        assertEquals("vegan", answers.dietType)
        assertEquals(listOf("peanuts"), answers.allergies)
        assertEquals(listOf("mushrooms"), answers.excludedIngredients)
        assertEquals(listOf("asian"), answers.cuisinePreferences)
        assertEquals(1800, answers.dailyCalorieTarget)
        assertEquals(4, answers.appetiteSatisfactionLevel)
        assertEquals(135, answers.macroTargets?.proteinGrams)
    }

    @Test
    fun `from an empty profile yields an empty draft`() {
        val answers = OnboardingAnswers.from(null)

        assertNull(answers.dietType)
        assertNull(answers.dailyCalorieTarget)
        assertTrue(answers.allergies.isEmpty())
        assertTrue(answers.cuisinePreferences.isEmpty())
        assertTrue(answers.excludedIngredients.isEmpty())
    }
}
