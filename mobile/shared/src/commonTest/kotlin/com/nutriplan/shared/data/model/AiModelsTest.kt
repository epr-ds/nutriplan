package com.nutriplan.shared.data.model

import kotlin.test.Test
import kotlin.test.assertEquals

class AiModelsTest {

    @Test
    fun `AiMealAnalysisRequest creates correctly`() {
        val request = AiMealAnalysisRequest(
            mealPhotoUrl = "https://example.com/photo.jpg",
            manualInput = "Grilled chicken with rice"
        )
        assertEquals("https://example.com/photo.jpg", request.mealPhotoUrl)
        assertEquals("Grilled chicken with rice", request.manualInput)
    }

    @Test
    fun `AiMealAnalysisResponse creates correctly`() {
        val response = AiMealAnalysisResponse(
            mealName = "Grilled Chicken Salad",
            calories = 450,
            macros = AiMacros(protein = 35, carbs = 20, fat = 15),
            confidence = 0.95,
            suggestions = listOf("Add more protein", "Consider adding healthy fats")
        )
        assertEquals("Grilled Chicken Salad", response.mealName)
        assertEquals(450, response.calories)
        assertEquals(35, response.macros.protein)
        assertEquals(20, response.macros.carbs)
        assertEquals(15, response.macros.fat)
        assertEquals(0.95, response.confidence)
        assertEquals(2, response.suggestions.size)
    }

    @Test
    fun `AiRecommendationsRequest creates correctly`() {
        val request = AiRecommendationsRequest(
            dietaryPreference = "keto",
            calorieTarget = 2000,
            allergies = listOf("nuts", "shellfish")
        )
        assertEquals("keto", request.dietaryPreference)
        assertEquals(2000, request.calorieTarget)
        assertEquals(2, request.allergies.size)
    }

    @Test
    fun `AiRecommendation creates correctly`() {
        val recommendation = AiRecommendation(
            recipeId = "recipe-123",
            recipeName = "Keto Avocado Bowl",
            reason = "High in healthy fats, low in carbs",
            matchScore = 0.92
        )
        assertEquals("recipe-123", recommendation.recipeId)
        assertEquals("Keto Avocado Bowl", recommendation.recipeName)
        assertEquals("High in healthy fats, low in carbs", recommendation.reason)
        assertEquals(0.92, recommendation.matchScore)
    }
}
