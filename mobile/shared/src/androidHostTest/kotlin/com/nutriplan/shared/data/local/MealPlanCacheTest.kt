package com.nutriplan.shared.data.local

import com.nutriplan.shared.data.model.PlanMealRecipe
import com.nutriplan.shared.testing.fullPlan
import com.nutriplan.shared.testing.meal
import com.nutriplan.shared.testing.newDatabase
import com.nutriplan.shared.testing.nutritionalSummary
import com.nutriplan.shared.testing.summary
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull

class MealPlanCacheTest {

    private val database = newDatabase()
    private val cache = MealPlanCache(database)

    @BeforeTest
    fun startEmpty() {
        assertEquals(emptyList(), cache.getPlans())
    }

    @Test
    fun `summaries are listed newest start date first`() {
        cache.upsertSummaries(listOf(summary("old", start = "2026-01-01"), summary("new", start = "2026-12-01")))

        assertEquals(listOf("new", "old"), cache.getPlans().map { it.id })
    }

    @Test
    fun `a summary alone is not a cached detail`() {
        cache.upsertSummaries(listOf(summary("p1")))

        assertNotNull(cache.getPlans().singleOrNull())
        assertNull(cache.getPlan("p1"))
    }

    @Test
    fun `a full plan round trips with its meals, nutrition and summary`() {
        val saved = fullPlan(
            id = "p1",
            meals = listOf(
                meal("m1", dayIndex = 0, type = "breakfast", recipe = PlanMealRecipe("r1", "Oats", "https://example.com/o.jpg")),
                meal("m2", dayIndex = null, type = "snack", calories = null),
            ),
            summary = nutritionalSummary(),
        )

        cache.upsertPlan(saved)

        assertEquals(saved, cache.getPlan("p1"))
        assertEquals(listOf(summary("p1").copy(name = "Plan p1")), cache.getPlans())
    }

    @Test
    fun `meals come back in the order the server sent them`() {
        cache.upsertPlan(fullPlan("p1", meals = listOf(meal("z"), meal("a"), meal("m"))))

        assertEquals(listOf("z", "a", "m"), cache.getPlan("p1")!!.meals.map { it.id })
    }

    @Test
    fun `saving a plan again replaces its meals`() {
        cache.upsertPlan(fullPlan("p1", meals = listOf(meal("m1"), meal("m2"))))
        cache.upsertPlan(fullPlan("p1", meals = listOf(meal("m3"))))

        assertEquals(listOf("m3"), cache.getPlan("p1")!!.meals.map { it.id })
    }

    @Test
    fun `refreshing summaries keeps the cached detail of the same plan`() {
        cache.upsertPlan(fullPlan("p1", meals = listOf(meal("m1")), summary = nutritionalSummary()))

        cache.upsertSummaries(listOf(summary("p1").copy(name = "Renamed", status = "completed")))

        val plan = cache.getPlan("p1")!!
        assertEquals("Renamed", plan.name)
        assertEquals("completed", plan.status)
        assertEquals(2000, plan.dailyCalorieTarget)
        assertEquals(listOf("m1"), plan.meals.map { it.id })
    }

    @Test
    fun `invalidating the detail keeps the summary but drops meals and detail`() {
        cache.upsertPlan(fullPlan("p1", meals = listOf(meal("m1"))))

        cache.invalidateDetail("p1")

        assertNull(cache.getPlan("p1"))
        assertEquals(listOf("p1"), cache.getPlans().map { it.id })

        // The detail comes back cleanly the next time the plan is saved.
        cache.upsertPlan(fullPlan("p1", meals = listOf(meal("m9"))))
        assertEquals(listOf("m9"), cache.getPlan("p1")!!.meals.map { it.id })
    }

    @Test
    fun `plan ids list every cached plan`() {
        cache.upsertSummaries(listOf(summary("a"), summary("b")))
        cache.upsertPlan(fullPlan("c"))

        assertEquals(setOf("a", "b", "c"), cache.getPlanIds().toSet())
    }

    @Test
    fun `delete removes the plan and its meals`() {
        cache.upsertPlan(fullPlan("p1", meals = listOf(meal("m1"))))

        cache.delete("p1")

        assertNull(cache.getPlan("p1"))
        assertEquals(emptyList(), cache.getPlans())
        assertEquals(0, database.mealPlanQueries.selectMealsForPlan("p1").executeAsList().size)
    }

    @Test
    fun `clear removes every plan and meal`() {
        cache.upsertPlan(fullPlan("p1", meals = listOf(meal("m1"))))
        cache.upsertSummaries(listOf(summary("p2")))

        cache.clear()

        assertEquals(emptyList(), cache.getPlans())
        assertNull(cache.getPlan("p1"))
    }

    @Test
    fun `unreadable cached json is dropped instead of crashing`() {
        cache.upsertPlan(fullPlan("p1"))
        database.mealPlanQueries.insertMeal(
            id = "bad",
            plan_id = "p1",
            position = 0,
            meal_type = "lunch",
            servings = 1.0,
            day_index = 0,
            satisfaction_level = null,
            recipe = "{not json",
            nutritional_info = "[1, 2",
        )

        val meals = cache.getPlan("p1")!!.meals

        assertEquals(listOf("bad"), meals.map { it.id })
        assertNull(meals.single().recipe)
        assertNull(meals.single().nutritionalInfo)
    }
}
