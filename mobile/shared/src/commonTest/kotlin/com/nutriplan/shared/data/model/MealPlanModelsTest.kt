package com.nutriplan.shared.data.model

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class MealPlanModelsTest {

    @Test
    fun `CreateMealPlanRequest creates correctly`() {
        val request = CreateMealPlanRequest(
            name = "Keto Plan",
            startDate = "2024-01-15",
            endDate = "2024-01-22",
            dietaryPreferences = listOf("keto"),
            targetCalories = 2000,
        )
        assertEquals("Keto Plan", request.name)
        assertEquals("2024-01-15", request.startDate)
        assertEquals("2024-01-22", request.endDate)
        assertEquals(listOf("keto"), request.dietaryPreferences)
        assertEquals(2000, request.targetCalories)
        assertNull(request.description)
    }

    @Test
    fun `UpdateMealPlanRequest only carries provided fields`() {
        val request = UpdateMealPlanRequest(name = "Updated Plan", targetCalories = 1800)
        assertEquals("Updated Plan", request.name)
        assertEquals(1800, request.targetCalories)
        assertNull(request.startDate)
        assertNull(request.dietaryPreferences)
    }

    @Test
    fun `MealPlanQuery creates correctly`() {
        val query = MealPlanQuery(status = "active", limit = 10, offset = 0)
        assertEquals("active", query.status)
        assertEquals(10, query.limit)
        assertEquals(0, query.offset)
    }

    @Test
    fun `AddMealRequest creates correctly`() {
        val request = AddMealRequest(
            recipeId = "recipe-1",
            mealType = "breakfast",
            scheduledDate = "2024-01-15",
            portionSize = 1.5,
        )
        assertEquals("recipe-1", request.recipeId)
        assertEquals("breakfast", request.mealType)
        assertEquals("2024-01-15", request.scheduledDate)
        assertEquals(1.5, request.portionSize)
    }

    @Test
    fun `MealPlan creates correctly`() {
        val plan = MealPlan(
            id = "plan-1",
            name = "Keto Plan",
            userId = "user-1",
            startDate = "2024-01-15",
            endDate = "2024-01-22",
            status = "active",
        )
        assertEquals("plan-1", plan.id)
        assertEquals("active", plan.status)
        assertNull(plan.meals)
    }
}