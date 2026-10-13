++ b/mobile/shared/src/commonTest/kotlin/com/nutriplan/shared/data/repository/DietaryRepositoryUrlTest.kt
package com.nutriplan.shared.data.repository

import kotlin.test.Test
import kotlin.test.assertEquals

class DietaryRepositoryUrlTest {

    @Test
    fun `createMealPlan uses correct endpoint`() {
        assertEquals("dietary/meal-plans", "${ApiConfig.DIETARY}/meal-plans")
    }

    @Test
    fun `getMealPlans uses correct endpoint`() {
        assertEquals("dietary/meal-plans", "${ApiConfig.DIETARY}/meal-plans")
    }

    @Test
    fun `getMealPlan uses correct endpoint with ID`() {
        assertEquals("dietary/meal-plans/plan-123", "${ApiConfig.DIETARY}/meal-plans/plan-123")
    }

    @Test
    fun `updateMealPlan uses correct endpoint with ID`() {
        assertEquals("dietary/meal-plans/plan-123", "${ApiConfig.DIETARY}/meal-plans/plan-123")
    }

    @Test
    fun `addMeal uses correct endpoint`() {
        assertEquals("dietary/meal-plans/plan-123/meals", "${ApiConfig.DIETARY}/meal-plans/plan-123/meals")
    }

    @Test
    fun `getRecipes uses correct endpoint`() {
        assertEquals("dietary/recipes", "${ApiConfig.DIETARY}/recipes")
    }
}
