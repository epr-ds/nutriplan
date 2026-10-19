package com.nutriplan.shared.planning

import com.nutriplan.shared.data.model.PlanMeal
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class MealPlanGroupingTest {

    private fun meal(
        id: String,
        date: String,
        type: String,
        calories: Int? = null,
    ) = PlanMeal(
        id = id,
        planId = "p1",
        recipeId = "r-$id",
        recipeName = "Recipe $id",
        mealType = type,
        scheduledDate = date,
        calories = calories,
    )

    @Test
    fun `no meals gives no days`() {
        assertEquals(emptyList(), groupMealsByDay(emptyList()))
    }

    @Test
    fun `days are sorted by date regardless of input order`() {
        val days = groupMealsByDay(
            listOf(
                meal("c", "2026-10-03", "LUNCH"),
                meal("a", "2026-10-01", "LUNCH"),
                meal("b", "2026-10-02", "LUNCH"),
            ),
        )

        assertEquals(listOf("2026-10-01", "2026-10-02", "2026-10-03"), days.map { it.date })
    }

    @Test
    fun `sections follow breakfast lunch dinner snack`() {
        val day = groupMealsByDay(
            listOf(
                meal("1", "2026-10-01", "SNACK"),
                meal("2", "2026-10-01", "DINNER"),
                meal("3", "2026-10-01", "BREAKFAST"),
                meal("4", "2026-10-01", "LUNCH"),
            ),
        ).single()

        assertEquals(listOf("BREAKFAST", "LUNCH", "DINNER", "SNACK"), day.sections.map { it.mealType })
    }

    @Test
    fun `unknown meal types come last, alphabetically`() {
        val day = groupMealsByDay(
            listOf(
                meal("1", "2026-10-01", "SUPPER"),
                meal("2", "2026-10-01", "BRUNCH"),
                meal("3", "2026-10-01", "DINNER"),
            ),
        ).single()

        assertEquals(listOf("DINNER", "BRUNCH", "SUPPER"), day.sections.map { it.mealType })
    }

    @Test
    fun `meal types match case-insensitively and are shown as sent`() {
        val day = groupMealsByDay(
            listOf(
                meal("1", "2026-10-01", "lunch"),
                meal("2", "2026-10-01", "LUNCH"),
            ),
        ).single()

        assertEquals(1, day.sections.size)
        assertEquals("lunch", day.sections.single().mealType)
        assertEquals(listOf("1", "2"), day.sections.single().meals.map { it.id })
    }

    @Test
    fun `meals in a section keep their arrival order`() {
        val section = groupMealsByDay(
            listOf(
                meal("z", "2026-10-01", "LUNCH"),
                meal("a", "2026-10-01", "LUNCH"),
                meal("m", "2026-10-01", "LUNCH"),
            ),
        ).single().sections.single()

        assertEquals(listOf("z", "a", "m"), section.meals.map { it.id })
    }

    @Test
    fun `day calories add up the known per-meal calories`() {
        val day = groupMealsByDay(
            listOf(
                meal("1", "2026-10-01", "BREAKFAST", calories = 300),
                meal("2", "2026-10-01", "LUNCH", calories = 600),
                meal("3", "2026-10-01", "DINNER", calories = null),
            ),
        ).single()

        assertEquals(900, day.totalCalories)
    }

    @Test
    fun `day calories are unknown, not zero, when no meal has them`() {
        val day = groupMealsByDay(listOf(meal("1", "2026-10-01", "LUNCH"))).single()

        assertNull(day.totalCalories)
    }
}
