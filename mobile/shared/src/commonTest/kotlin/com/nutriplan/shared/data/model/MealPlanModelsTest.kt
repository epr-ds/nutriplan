package com.nutriplan.shared.data.model

import kotlin.test.Test
import kotlin.test.assertEquals

class MealPlanModelsTest {

    @Test
    fun `CreateMealPlanRequest creates correctly`() {
        val request = CreateMealPlanRequest(
            name = "Keto Plan",
            durationDays = 7,
            dietaryPreference = "keto",
            dailyCalories = 2000,
            targetAudience = "adult"
        )
        assertEquals("Keto Plan", request.name)
        assertEquals(7, request.durationDays)
        assertEquals("keto", request.dietaryPreference)
        assertEquals(2000, request.dailyCalories)
        assertEquals("adult", request.targetAudience)
    }

    @Test
    fun `UpdateMealPlanRequest creates correctly`() {
        val request = UpdateMealPlanRequest(
            name = "Updated Plan",
            dietaryPreference = "vegan",
            dailyCalories = 1800
        )
        assertEquals("Updated Plan", request.name)
        assertEquals("vegan", request.dietaryPreference)
        assertEquals(1800, request.dailyCalories)
    }

    @Test
    fun `MealPlanQuery creates correctly`() {
        val query = MealPlanQuery(
            status = "active",
            limit = 10,
            offset = 0
        )
        assertEquals("active", query.status)
        assertEquals(10, query.limit)
        assertEquals(0, query.offset)
    }

    @Test
    fun `AddMealRequest creates correctly`() {
        val request = AddMealRequest(
            mealType = "breakfast",
            foodItems = listOf("oatmeal", "banana"),
            calories = 350
        )
        assertEquals("breakfast", request.mealType)
        assertEquals(2, request.foodItems.size)
        assertEquals(350, request.calories)
    }
}
