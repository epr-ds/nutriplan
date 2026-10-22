package com.nutriplan.shared.data.local

import app.cash.sqldelight.driver.jdbc.sqlite.JdbcSqliteDriver
import com.nutriplan.db.NutriPlanDatabase
import com.nutriplan.shared.data.model.PlanMealRecipe
import com.nutriplan.shared.testing.addRequest
import com.nutriplan.shared.testing.favoriteRecipe
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
    fun `the schema is version 6 now that offline favorite toggles are queued too`() {
        assertEquals(6L, NutriPlanDatabase.Schema.version)
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

    @Test
    fun `a version 2 database gains the favorites cache and keeps its cached plans`() {
        val driver = JdbcSqliteDriver(JdbcSqliteDriver.IN_MEMORY)
        // The tables exactly as version 2 created them (no favorites yet).
        driver.execute(
            null,
            """
            CREATE TABLE meal_plan (
                id TEXT NOT NULL PRIMARY KEY, name TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL,
                status TEXT NOT NULL, daily_calorie_target INTEGER, nutritional_summary TEXT,
                has_detail INTEGER NOT NULL DEFAULT 0
            )
            """.trimIndent(),
            0,
        )
        driver.execute(
            null,
            """
            CREATE TABLE plan_meal (
                id TEXT NOT NULL PRIMARY KEY, plan_id TEXT NOT NULL, position INTEGER NOT NULL, meal_type TEXT NOT NULL,
                servings REAL NOT NULL, day_index INTEGER, satisfaction_level INTEGER, recipe TEXT, nutritional_info TEXT
            )
            """.trimIndent(),
            0,
        )
        driver.execute(
            null,
            "INSERT INTO meal_plan(id, name, start_date, end_date, status) " +
                "VALUES ('kept', 'Kept plan', '2026-10-01', '2026-10-07', 'active')",
            0,
        )

        NutriPlanDatabase.Schema.migrate(driver, 2L, 3L)

        val database = NutriPlanDatabase(driver)
        assertEquals(listOf("kept"), MealPlanCache(database).getPlans().map { it.id }, "plans survive the upgrade")
        val favorites = FavoriteRecipeCache(database)
        assertEquals(emptyList(), favorites.getAll())
        favorites.addFirst(favoriteRecipe("f1"))
        assertEquals(listOf("f1"), favorites.getAll().map { it.id })
    }

    @Test
    fun `a version 3 database gains the offline queue and keeps its plans and favorites`() {
        val driver = JdbcSqliteDriver(JdbcSqliteDriver.IN_MEMORY)
        // The tables as version 3 created them (no pending_meal yet).
        driver.execute(
            null,
            """
            CREATE TABLE meal_plan (
                id TEXT NOT NULL PRIMARY KEY, name TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL,
                status TEXT NOT NULL, daily_calorie_target INTEGER, nutritional_summary TEXT,
                has_detail INTEGER NOT NULL DEFAULT 0
            )
            """.trimIndent(),
            0,
        )
        driver.execute(
            null,
            "CREATE TABLE favorite_recipe (recipe_id TEXT NOT NULL PRIMARY KEY, position INTEGER NOT NULL, recipe TEXT NOT NULL)",
            0,
        )
        driver.execute(
            null,
            "INSERT INTO meal_plan(id, name, start_date, end_date, status) " +
                "VALUES ('kept', 'Kept plan', '2026-10-01', '2026-10-07', 'active')",
            0,
        )
        driver.execute(
            null,
            "INSERT INTO favorite_recipe(recipe_id, position, recipe) VALUES ('f1', 0, '{\"id\":\"f1\",\"name\":\"Soup\"}')",
            0,
        )

        NutriPlanDatabase.Schema.migrate(driver, 3L, 4L)

        val database = NutriPlanDatabase(driver)
        assertEquals(listOf("kept"), MealPlanCache(database).getPlans().map { it.id }, "plans survive the upgrade")
        assertEquals(listOf("f1"), FavoriteRecipeCache(database).getAll().map { it.id }, "favorites survive too")
        val queue = PendingMealStore(database)
        assertEquals(emptyList(), queue.waiting())
        queue.enqueue("kept", addRequest(), null, PlanMealRecipe(id = "r1", name = "Soup"), null)
        assertEquals(1, queue.waiting().size)
    }

    @Test
    fun `a version 4 database gains the queue of changes and keeps the queue of added meals`() {
        val driver = JdbcSqliteDriver(JdbcSqliteDriver.IN_MEMORY)
        // The tables as version 4 created them (no pending_change yet).
        driver.execute(
            null,
            """
            CREATE TABLE pending_meal (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, plan_id TEXT NOT NULL, meal_type TEXT NOT NULL,
                recipe_id TEXT NOT NULL, servings REAL NOT NULL, day_index INTEGER, recipe TEXT NOT NULL,
                nutritional_info TEXT, attempts INTEGER NOT NULL DEFAULT 0, remote_meal_id TEXT, failure TEXT
            )
            """.trimIndent(),
            0,
        )
        driver.execute(
            null,
            "INSERT INTO pending_meal(plan_id, meal_type, recipe_id, servings, recipe) " +
                "VALUES ('p1', 'lunch', 'r1', 1.0, '{\"id\":\"r1\",\"name\":\"Soup\"}')",
            0,
        )

        NutriPlanDatabase.Schema.migrate(driver, 4L, 5L)

        val database = NutriPlanDatabase(driver)
        assertEquals(listOf("r1"), PendingMealStore(database).waiting().map { it.recipeId }, "queued meals survive")
        val changes = PendingChangeStore(database)
        assertEquals(emptyList(), changes.waiting())
        changes.queueRemove("p1", com.nutriplan.shared.testing.meal("m1"))
        assertEquals(1, changes.waiting().size)
    }

    @Test
    fun `a version 5 database gains the queue of favorite toggles and keeps its favorites`() {
        val driver = JdbcSqliteDriver(JdbcSqliteDriver.IN_MEMORY)
        driver.execute(
            null,
            "CREATE TABLE favorite_recipe (recipe_id TEXT NOT NULL PRIMARY KEY, position INTEGER NOT NULL, recipe TEXT NOT NULL)",
            0,
        )
        driver.execute(
            null,
            "INSERT INTO favorite_recipe(recipe_id, position, recipe) VALUES ('f1', 0, '{\"id\":\"f1\",\"name\":\"Soup\"}')",
            0,
        )

        NutriPlanDatabase.Schema.migrate(driver, 5L, 6L)

        val database = NutriPlanDatabase(driver)
        assertEquals(listOf("f1"), FavoriteRecipeCache(database).getAll().map { it.id }, "favorites survive")
        val queue = PendingFavoriteStore(database)
        queue.queue(favoriteRecipe("f2"), favorite = true)
        assertEquals(listOf("f2"), queue.waiting().map { it.recipe.id })
    }
}
