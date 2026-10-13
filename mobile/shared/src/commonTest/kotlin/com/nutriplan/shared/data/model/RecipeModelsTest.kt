package com.nutriplan.shared.data.model

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class RecipeModelsTest {

    @Test
    fun `RecipeSearchQuery has pagination defaults`() {
        val query = RecipeSearchQuery()
        assertEquals(emptyList(), query.ingredients)
        assertNull(query.dietType)
        assertEquals(1, query.page)
        assertEquals(20, query.limit)
    }

    @Test
    fun `RecipeSearchQuery creates correctly`() {
        val query = RecipeSearchQuery(
            ingredients = listOf("chicken", "rice"),
            dietType = "high-protein",
            maxCalories = 600,
            minProtein = 30.0,
        )
        assertEquals(listOf("chicken", "rice"), query.ingredients)
        assertEquals("high-protein", query.dietType)
        assertEquals(600, query.maxCalories)
        assertEquals(30.0, query.minProtein)
    }

    @Test
    fun `RecipeResponse creates correctly`() {
        val recipe = RecipeResponse(
            id = "recipe-123",
            name = "Grilled Chicken Salad",
            description = "Healthy grilled chicken with mixed greens",
            servings = 2,
            prepTimeMinutes = 15,
            cookTimeMinutes = 20,
            nutritionPerServing = NutritionPerServing(calories = 450, protein = 35.0, carbs = 20.0, fat = 15.0, sugar = 4.0),
            ingredients = listOf(
                RecipeIngredient(name = "Chicken", quantity = 200.0, unit = "g", calories = null, protein = null, carbs = null, fat = null),
            ),
            instructions = listOf("Grill the chicken", "Toss with greens"),
            tags = listOf("high-protein"),
            dietType = "high-protein",
            imageUrl = "https://example.com/image.jpg",
            createdAt = "2024-01-15T10:00:00Z",
        )
        assertEquals("recipe-123", recipe.id)
        assertEquals(15, recipe.prepTimeMinutes)
        assertEquals(20, recipe.cookTimeMinutes)
        assertEquals(2, recipe.servings)
        assertEquals(450, recipe.nutritionPerServing.calories)
        assertEquals(1, recipe.ingredients.size)
        assertEquals(2, recipe.instructions.size)
        assertEquals("https://example.com/image.jpg", recipe.imageUrl)
    }
}