package com.nutriplan.shared.data.repository

import app.cash.sqldelight.driver.jdbc.sqlite.JdbcSqliteDriver
import com.nutriplan.db.NutriPlanDatabase
import com.nutriplan.shared.data.local.MealPlanCache
import com.nutriplan.shared.data.model.AddMealRequest
import com.nutriplan.shared.data.model.CreateMealPlanRequest
import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.model.MealPlanQuery
import com.nutriplan.shared.data.model.PlanMeal
import com.nutriplan.shared.data.model.Recipe
import com.nutriplan.shared.data.model.RecipeQuery
import com.nutriplan.shared.data.model.UpdateMealPlanRequest
import com.nutriplan.shared.data.network.ApiException
import kotlinx.coroutines.test.runTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotNull
import kotlin.test.assertNull

class CachedDietaryRepositoryTest {

    private class FakeDietary : DietaryRepository {
        var plans: List<MealPlan> = emptyList()
        var failure: Throwable? = null

        override suspend fun createMealPlan(request: CreateMealPlanRequest): MealPlan {
            failure?.let { throw it }
            return plans.first()
        }

        override suspend fun getMealPlans(query: MealPlanQuery?): List<MealPlan> {
            failure?.let { throw it }
            return plans
        }

        override suspend fun getMealPlan(planId: String): MealPlan {
            failure?.let { throw it }
            return plans.firstOrNull { it.id == planId } ?: throw ApiException.HttpError(404, null)
        }

        override suspend fun updateMealPlan(planId: String, request: UpdateMealPlanRequest): MealPlan {
            failure?.let { throw it }
            return plans.first { it.id == planId }
        }

        override suspend fun addMeal(planId: String, request: AddMealRequest): Any {
            failure?.let { throw it }
            return Unit
        }

        override suspend fun getRecipes(query: RecipeQuery?): List<Recipe> = emptyList()
    }

    private val remote = FakeDietary()
    private lateinit var cache: MealPlanCache
    private lateinit var repository: CachedDietaryRepository

    @BeforeTest
    fun setUp() {
        val driver = JdbcSqliteDriver(JdbcSqliteDriver.IN_MEMORY)
        NutriPlanDatabase.Schema.create(driver)
        cache = MealPlanCache(NutriPlanDatabase(driver))
        repository = CachedDietaryRepository(remote, cache)
    }

    private fun plan(
        id: String,
        start: String = "2026-10-01",
        status: String = "ACTIVE",
        meals: List<PlanMeal>? = null,
    ) = MealPlan(
        id = id,
        name = "Plan $id",
        userId = "user-1",
        startDate = start,
        endDate = "2026-10-07",
        meals = meals,
        status = status,
    )

    private fun meal(id: String, planId: String) = PlanMeal(
        id = id,
        planId = planId,
        recipeId = "r-$id",
        recipeName = "Recipe $id",
        mealType = "LUNCH",
        scheduledDate = "2026-10-02",
    )

    private val offline = ApiException.NetworkError()

    @Test
    fun `online listing is returned and cached for offline use`() = runTest {
        remote.plans = listOf(plan("p1", meals = listOf(meal("m1", "p1"))), plan("p2", start = "2026-11-01"))
        assertEquals(remote.plans, repository.getMealPlans())

        remote.failure = offline
        assertEquals(listOf("p2", "p1"), repository.getMealPlans().map { it.id })
        assertEquals(listOf("m1"), repository.getMealPlan("p1").meals!!.map { it.id })
    }

    @Test
    fun `offline with an empty cache rethrows instead of returning an empty list`() = runTest {
        remote.failure = offline

        assertFailsWith<ApiException.NetworkError> { repository.getMealPlans() }
        assertFailsWith<ApiException.NetworkError> { repository.getMealPlan("p1") }
    }

    @Test
    fun `server errors fall back to the cache`() = runTest {
        remote.plans = listOf(plan("p1"))
        repository.getMealPlans()

        remote.failure = ApiException.HttpError(500, "boom")
        assertEquals(listOf("p1"), repository.getMealPlans().map { it.id })
    }

    @Test
    fun `auth errors are surfaced and do not fall back to the cache`() = runTest {
        remote.plans = listOf(plan("p1"))
        repository.getMealPlans()

        remote.failure = ApiException.HttpError(401, null)
        assertFailsWith<ApiException.HttpError> { repository.getMealPlans() }
        assertFailsWith<ApiException.HttpError> { repository.getMealPlan("p1") }
        assertNotNull(cache.getPlan("p1"))
    }

    @Test
    fun `a 404 evicts the cached plan`() = runTest {
        remote.plans = listOf(plan("p1"))
        repository.getMealPlan("p1")
        assertNotNull(cache.getPlan("p1"))

        remote.plans = emptyList()
        assertFailsWith<ApiException.HttpError> { repository.getMealPlan("p1") }
        assertNull(cache.getPlan("p1"))
    }

    @Test
    fun `full listing prunes plans removed on the server but keeps unsynced local ones`() = runTest {
        remote.plans = listOf(plan("keep"), plan("gone"))
        repository.getMealPlans()
        cache.upsert(plan("local-draft"), synced = false)

        remote.plans = listOf(plan("keep"))
        repository.getMealPlans()

        assertEquals(setOf("keep", "local-draft"), cache.getPlans().map { it.id }.toSet())
    }

    @Test
    fun `filtered listing does not prune the cache`() = runTest {
        remote.plans = listOf(plan("a"), plan("b"))
        repository.getMealPlans()

        remote.plans = listOf(plan("a"))
        repository.getMealPlans(MealPlanQuery(status = "ACTIVE"))

        assertEquals(setOf("a", "b"), cache.getPlans().map { it.id }.toSet())
    }

    @Test
    fun `offline listing honours status filter and paging`() = runTest {
        remote.plans = listOf(
            plan("a", start = "2026-04-01", status = "ACTIVE"),
            plan("b", start = "2026-03-01", status = "DRAFT"),
            plan("c", start = "2026-02-01", status = "ACTIVE"),
            plan("d", start = "2026-01-01", status = "ACTIVE"),
        )
        repository.getMealPlans()
        remote.failure = offline

        assertEquals(listOf("a", "c", "d"), repository.getMealPlans(MealPlanQuery(status = "ACTIVE")).map { it.id })
        assertEquals(listOf("c"), repository.getMealPlans(MealPlanQuery(status = "ACTIVE", limit = 1, offset = 1)).map { it.id })
    }

    @Test
    fun `cached meals are kept when the server response omits them`() = runTest {
        remote.plans = listOf(plan("p1", meals = listOf(meal("m1", "p1"))))
        repository.getMealPlan("p1")

        remote.plans = listOf(plan("p1", meals = null))
        repository.getMealPlan("p1")

        assertEquals(listOf("m1"), cache.getPlan("p1")!!.meals!!.map { it.id })
    }

    @Test
    fun `created and updated plans are cached as synced`() = runTest {
        remote.plans = listOf(plan("p1"))
        repository.createMealPlan(CreateMealPlanRequest(name = "n", startDate = "2026-10-01", endDate = "2026-10-07"))
        assertNotNull(cache.getPlan("p1"))
        assertEquals(emptyList(), cache.getUnsyncedPlans())

        remote.plans = listOf(plan("p1").copy(name = "renamed"))
        repository.updateMealPlan("p1", UpdateMealPlanRequest(name = "renamed"))
        assertEquals("renamed", cache.getPlan("p1")!!.name)
    }

    @Test
    fun `adding a meal invalidates the cached plan`() = runTest {
        remote.plans = listOf(plan("p1", meals = listOf(meal("m1", "p1"))))
        repository.getMealPlan("p1")

        repository.addMeal("p1", AddMealRequest(recipeId = "r", mealType = "LUNCH", scheduledDate = "2026-10-02"))

        assertNull(cache.getPlan("p1"))
    }
}
