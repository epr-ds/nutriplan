package com.nutriplan.shared.data.local

import app.cash.sqldelight.driver.jdbc.sqlite.JdbcSqliteDriver
import com.nutriplan.db.NutriPlanDatabase
import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.model.PlanMeal
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class MealPlanCacheTest {

    private lateinit var cache: MealPlanCache

    @BeforeTest
    fun setUp() {
        val driver = JdbcSqliteDriver(JdbcSqliteDriver.IN_MEMORY)
        NutriPlanDatabase.Schema.create(driver)
        cache = MealPlanCache(NutriPlanDatabase(driver))
    }

    private fun plan(id: String, start: String = "2026-10-01", meals: List<PlanMeal>? = null) = MealPlan(
        id = id,
        name = "Plan $id",
        description = "desc",
        userId = "user-1",
        startDate = start,
        endDate = "2026-10-07",
        dietaryPreferences = listOf("vegan", "gluten-free"),
        targetCalories = 2000,
        meals = meals,
        status = "ACTIVE",
        createdAt = "2026-09-30T10:00:00Z",
        updatedAt = null,
    )

    private fun meal(id: String, planId: String, type: String = "BREAKFAST") = PlanMeal(
        id = id,
        planId = planId,
        recipeId = "r-$id",
        recipeName = "Recipe $id",
        mealType = type,
        scheduledDate = "2026-10-02",
        portionSize = 1.5,
        calories = 450,
    )

    @Test
    fun `upsert then read returns the same plan with meals`() {
        val saved = plan("p1", meals = listOf(meal("m1", "p1"), meal("m2", "p1", "LUNCH")))
        cache.upsert(saved, synced = true)

        assertEquals(saved.copy(meals = saved.meals!!.sortedBy { it.mealType }), cache.getPlan("p1"))
    }

    @Test
    fun `upsert replaces previous meals`() {
        cache.upsert(plan("p1", meals = listOf(meal("m1", "p1"), meal("m2", "p1"))), synced = true)
        cache.upsert(plan("p1", meals = listOf(meal("m3", "p1"))), synced = true)

        assertEquals(listOf("m3"), cache.getPlan("p1")!!.meals!!.map { it.id })
    }

    @Test
    fun `plans are ordered by start date descending`() {
        cache.upsert(plan("old", start = "2026-01-01"), synced = true)
        cache.upsert(plan("new", start = "2026-12-01"), synced = true)

        assertEquals(listOf("new", "old"), cache.getPlans().map { it.id })
    }

    @Test
    fun `unsynced plans are listed until marked synced`() {
        cache.upsert(plan("local"), synced = false)
        cache.upsert(plan("remote"), synced = true)
        assertEquals(listOf("local"), cache.getUnsyncedPlans().map { it.id })

        cache.markSynced("local")
        assertEquals(emptyList(), cache.getUnsyncedPlans())
    }

    @Test
    fun `delete removes the plan and its meals`() {
        cache.upsert(plan("p1", meals = listOf(meal("m1", "p1"))), synced = true)
        cache.delete("p1")

        assertNull(cache.getPlan("p1"))
        assertEquals(emptyList(), cache.getPlans())
    }

    @Test
    fun `optional fields round trip as null`() {
        val bare = plan("p1").copy(description = null, dietaryPreferences = null, targetCalories = null)
        cache.upsert(bare, synced = true)

        assertEquals(bare.copy(meals = emptyList()), cache.getPlan("p1"))
    }
}
