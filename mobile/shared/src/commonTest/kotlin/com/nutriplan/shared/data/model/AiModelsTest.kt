package com.nutriplan.shared.data.model

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class AiModelsTest {

    @Test
    fun `AnalyzeMealRequest creates correctly`() {
        val request = AnalyzeMealRequest(
            mealDescription = "Grilled chicken with rice",
            imageUrl = "https://example.com/photo.jpg",
        )
        assertEquals("Grilled chicken with rice", request.mealDescription)
        assertEquals("https://example.com/photo.jpg", request.imageUrl)
    }

    @Test
    fun `AnalyzeMealResponse creates correctly`() {
        val response = AnalyzeMealResponse(
            detectedFoods = listOf(DetectedFood(name = "Chicken", estimatedAmount = "150 g", calories = 250)),
            nutritionEstimate = NutritionInfo(calories = 450, protein = 35.0, carbohydrates = 20.0, fat = 15.0),
            confidence = 0.95,
        )
        assertEquals(1, response.detectedFoods?.size)
        assertEquals("Chicken", response.detectedFoods?.first()?.name)
        assertEquals(450, response.nutritionEstimate?.calories)
        assertEquals(0.95, response.confidence)
    }

    @Test
    fun `RecommendationsRequest optional fields default to null`() {
        val request = RecommendationsRequest(
            dietaryPreferences = listOf("keto"),
            calorieTarget = 2000,
        )
        assertEquals(listOf("keto"), request.dietaryPreferences)
        assertEquals(2000, request.calorieTarget)
        assertNull(request.mealType)
        assertNull(request.maxResults)
    }

    @Test
    fun `RecommendationResult creates correctly`() {
        val result = RecommendationResult(
            recipeId = "recipe-123",
            recipeName = "Keto Avocado Bowl",
            reason = "High in healthy fats, low in carbs",
            matchScore = 0.92,
        )
        assertEquals("recipe-123", result.recipeId)
        assertEquals("Keto Avocado Bowl", result.recipeName)
        assertEquals("High in healthy fats, low in carbs", result.reason)
        assertEquals(0.92, result.matchScore)
    }
}