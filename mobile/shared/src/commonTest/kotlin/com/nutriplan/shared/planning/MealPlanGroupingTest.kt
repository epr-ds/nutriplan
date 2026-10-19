package com.nutriplan.shared.planning

import com.nutriplan.shared.data.model.NutritionalInfo
import com.nutriplan.shared.data.model.PlanMeal
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class MealPlanGroupingTest {

    private fun meal(
        id: String,
        dayIndex: Int?,
        type: String,
        calories: Int? = null,
    ) = PlanMeal(
        id = id,
        mealType = type,
        servings = 1.0,
        dayIndex = dayIndex,
        nutritionalInfo = calories?.let { NutritionalInfo(calories = it) },
    )

    private val start = "2026-10-01"

    @Test
    fun `no meals gives no days`() {
        assertEquals(emptyList(), groupMealsByDay(start, emptyList()))
    }

    @Test
    fun `days are sorted by day index regardless of input order`() {
        val days = groupMealsByDay(
            start,
            listOf(meal("c", 2, "lunch"), meal("a", 0, "lunch"), meal("b", 1, "lunch")),
        )

        assertEquals(listOf(0, 1, 2), days.map { it.dayIndex })
    }

    @Test
    fun `a day's date is the plan start plus its index`() {
        val days = groupMealsByDay(
            start,
            listOf(meal("a", 0, "lunch"), meal("b", 6, "lunch"), meal("c", 31, "lunch")),
        )

        assertEquals(listOf("2026-10-01", "2026-10-07", "2026-11-01"), days.map { it.date })
    }

    @Test
    fun `an unparseable start date leaves the dates unknown instead of failing`() {
        val day = groupMealsByDay("soon", listOf(meal("a", 0, "lunch"))).single()

        assertEquals(0, day.dayIndex)
        assertNull(day.date)
    }

    @Test
    fun `meals without a day come last as one unassigned day`() {
        val days = groupMealsByDay(
            start,
            listOf(meal("x", null, "snack"), meal("a", 1, "lunch"), meal("y", null, "lunch")),
        )

        assertEquals(listOf(1, null), days.map { it.dayIndex })
        val unassigned = days.last()
        assertNull(unassigned.date)
        assertEquals(setOf("x", "y"), unassigned.sections.flatMap { it.meals }.map { it.id }.toSet())
    }

    @Test
    fun `sections follow breakfast lunch dinner snack`() {
        val day = groupMealsByDay(
            start,
            listOf(meal("1", 0, "snack"), meal("2", 0, "dinner"), meal("3", 0, "breakfast"), meal("4", 0, "lunch")),
        ).single()

        assertEquals(listOf("breakfast", "lunch", "dinner", "snack"), day.sections.map { it.mealType })
    }

    @Test
    fun `unknown meal types come last, alphabetically`() {
        val day = groupMealsByDay(
            start,
            listOf(meal("1", 0, "supper"), meal("2", 0, "brunch"), meal("3", 0, "dinner")),
        ).single()

        assertEquals(listOf("dinner", "brunch", "supper"), day.sections.map { it.mealType })
    }

    @Test
    fun `meal types match case-insensitively and are shown as sent`() {
        val day = groupMealsByDay(
            start,
            listOf(meal("1", 0, "lunch"), meal("2", 0, "LUNCH")),
        ).single()

        assertEquals(1, day.sections.size)
        assertEquals("lunch", day.sections.single().mealType)
        assertEquals(listOf("1", "2"), day.sections.single().meals.map { it.id })
    }

    @Test
    fun `meals in a section keep their arrival order`() {
        val section = groupMealsByDay(
            start,
            listOf(meal("z", 0, "lunch"), meal("a", 0, "lunch"), meal("m", 0, "lunch")),
        ).single().sections.single()

        assertEquals(listOf("z", "a", "m"), section.meals.map { it.id })
    }

    @Test
    fun `day calories add up the known per-meal calories`() {
        val day = groupMealsByDay(
            start,
            listOf(
                meal("1", 0, "breakfast", calories = 300),
                meal("2", 0, "lunch", calories = 600),
                meal("3", 0, "dinner", calories = null),
            ),
        ).single()

        assertEquals(900, day.totalCalories)
    }

    @Test
    fun `day calories are unknown, not zero, when no meal has them`() {
        val day = groupMealsByDay(start, listOf(meal("1", 0, "lunch"))).single()

        assertNull(day.totalCalories)
    }
}
