package com.nutriplan.shared.data.model

import kotlin.test.Test
import kotlin.test.assertEquals

class RecipeModelsTest {

    @Test
    fun `RecipeQuery creates correctly`() {
        val query = RecipeQuery(
            dietaryPreference = "vegetarian",
            calorieRangeMin = 300,
            calorieRangeMax = 600,
            limit = 20,
            offset = 0
        )
        assertEquals("vegetarian", query.dietaryPreference)
        assertEquals(300, query.calorieRangeMin)
        assertEquals(600, query.calorieRangeMax)
        assertEquals(20, query.limit)
        assertEquals(0, query.offset)
    }

    @Test
    fun `Recipe creates correctly`() {
        val recipe = Recipe(
            id = "recipe-123",
            name = "Grilled Chicken Salad",
            description = "Healthy grilled chicken with mixed greens",
            prepTimeMinutes = 15,
            cookTimeMinutes = 20,
            servings = 2,
            dietaryPreference = "high-protein",
            caloriesPerServing = 450,
            imageUrl = "https://example.com/image.jpg"
        )
        assertEquals("recipe-123", recipe.id)
        assertEquals("Grilled Chicken Salad", recipe.name)
        assertEquals(15, recipe.prepTimeMinutes)
        assertEquals(20, recipe.cookTimeMinutes)
        assertEquals(2, recipe.servings)
        assertEquals("high-protein", recipe.dietaryPreference)
        assertEquals(450, recipe.caloriesPerServing)
        assertEquals("https://example.com/image.jpg", recipe.imageUrl)
    }
}
