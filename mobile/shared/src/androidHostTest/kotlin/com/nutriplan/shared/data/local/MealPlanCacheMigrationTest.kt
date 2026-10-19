package com.nutriplan.shared.data.local

import app.cash.sqldelight.driver.jdbc.sqlite.JdbcSqliteDriver
import com.nutriplan.db.NutriPlanDatabase
import com.nutriplan.shared.testing.fullPlan
import com.nutriplan.shared.testing.meal
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull

/**
 * An app updated from the build that cached the old, contract-mismatched plan model must open its
 * existing database and work, instead of crashing on columns that no longer exist.
 */
class MealPlanCacheMigrationTest {

    @Test
    fun `the schema is version 2 now that the cache shape changed`() {
        assertEquals(2L, NutriPlanDatabase.Schema.version)
    }

    @Test
    fun `a version 1 database migrates to a working version 2 cache`() {
        val driver = JdbcSqliteDriver(JdbcSqliteDriver.IN_MEMORY)
        // The tables exactly as the shipped version 1 created them.
        driver.execute(
            null,
            """
            CREATE TABLE meal_plan (
                id TEXT NOT NULL PRIMARY KEY, name TEXT NOT NULL, description TEXT, user_id TEXT NOT NULL,
                start_date TEXT NOT NULL, end_date TEXT NOT NULL, dietary_preferences TEXT, target_calories INTEGER,
                status TEXT NOT NULL, created_at TEXT, updated_at TEXT, synced INTEGER NOT NULL DEFAULT 0
            )
            """.trimIndent(),
            0,
        )
        driver.execute(
            null,
            """
            CREATE TABLE plan_meal (
                id TEXT NOT NULL PRIMARY KEY, plan_id TEXT NOT NULL, recipe_id TEXT NOT NULL, recipe_name TEXT NOT NULL,
                meal_type TEXT NOT NULL, scheduled_date TEXT NOT NULL, portion_size REAL, calories INTEGER
            )
            """.trimIndent(),
            0,
        )
        driver.execute(
            null,
            "INSERT INTO meal_plan(id, name, user_id, start_date, end_date, status) " +
                "VALUES ('old', 'Old plan', 'u1', '2026-10-01', '2026-10-07', 'ACTIVE')",
            0,
        )

        NutriPlanDatabase.Schema.migrate(driver, 1L, 2L)

        val cache = MealPlanCache(NutriPlanDatabase(driver))
        assertEquals(emptyList(), cache.getPlans(), "the old cache content is discarded; the next refresh repopulates it")

        cache.upsertPlan(fullPlan("p1", meals = listOf(meal("m1"))))
        assertNotNull(cache.getPlan("p1"))
        assertEquals(listOf("m1"), cache.getPlan("p1")!!.meals.map { it.id })
    }
}
