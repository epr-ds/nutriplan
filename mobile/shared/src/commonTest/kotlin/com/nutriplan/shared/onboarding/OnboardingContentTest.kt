package com.nutriplan.shared.onboarding

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class OnboardingContentTest {

    @Test
    fun `diet types match the contract enum`() {
        assertEquals(
            listOf("omnivore", "vegetarian", "vegan", "keto", "paleo", "mediterranean"),
            OnboardingContent.dietTypes.map { it.value },
        )
    }

    @Test
    fun `cuisines match the contract enum`() {
        assertEquals(
            listOf("mexican", "italian", "asian", "mediterranean", "american", "indian"),
            OnboardingContent.cuisines.map { it.value },
        )
    }

    @Test
    fun `catalogs use unique values`() {
        for (catalog in listOf(OnboardingContent.dietTypes, OnboardingContent.cuisines, OnboardingContent.commonAllergens)) {
            val values = catalog.map { it.value }
            assertEquals(values.size, values.toSet().size, "duplicate value in $values")
        }
    }

    @Test
    fun `every option has both labels`() {
        val catalogs = listOf(
            OnboardingContent.dietTypes,
            OnboardingContent.cuisines,
            OnboardingContent.commonAllergens,
            OnboardingContent.commonExcludedIngredients,
        )
        assertTrue(catalogs.flatten().all { it.labelEn.isNotBlank() && it.labelEs.isNotBlank() })
    }
}
