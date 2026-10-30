package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.local.MealPlanCache
import com.nutriplan.shared.data.model.AddMealRequest
import com.nutriplan.shared.data.model.UpdateMealRequest
import com.nutriplan.shared.data.model.CreateMealPlanRequest
import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.model.MealPlanQuery
import com.nutriplan.shared.data.model.MealPlanSummary
import com.nutriplan.shared.data.model.PlanMeal
import com.nutriplan.shared.data.model.NutritionDisclaimer
import com.nutriplan.shared.data.model.Recipe
import com.nutriplan.shared.data.model.RecipeSearchQuery
import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.testing.fullPlan
import com.nutriplan.shared.testing.meal
import com.nutriplan.shared.testing.newCache
import com.nutriplan.shared.testing.summary
import kotlinx.coroutines.test.runTest
import kotlin.coroutines.cancellation.CancellationException
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotNull
import kotlin.test.assertNull

class CachedDietaryRepositoryTest {

    private class FakeDietary : DietaryRepository {
        var summaries: List<MealPlanSummary> = emptyList()
        var plan: MealPlan? = null
        var failure: Throwable? = null
        var lastQuery: MealPlanQuery? = null

        override suspend fun getMealPlans(query: MealPlanQuery?): List<MealPlanSummary> {
            lastQuery = query
            failure?.let { throw it }
            return summaries
        }

        override suspend fun getMealPlan(planId: String): MealPlan {
            failure?.let { throw it }
            return plan?.takeIf { it.id == planId } ?: throw ApiException.HttpError(404, null)
        }

        override suspend fun createMealPlan(request: CreateMealPlanRequest): MealPlan {
            failure?.let { throw it }
            return plan!!
        }

        override suspend fun updateMealPlanStatus(planId: String, status: String): MealPlan {
            failure?.let { throw it }
            return plan!!.copy(status = status)
        }

        override suspend fun addMeal(planId: String, request: AddMealRequest): PlanMeal {
            failure?.let { throw it }
            return meal("new")
        }

        override suspend fun removeMeal(planId: String, mealId: String) {
            failure?.let { throw it }
        }
        override suspend fun updateMeal(planId: String, mealId: String, request: UpdateMealRequest): PlanMeal {
            failure?.let { throw it }
            return meal(mealId)
        }

        override suspend fun searchRecipes(query: RecipeSearchQuery): List<Recipe> = emptyList()
        override suspend fun getRecipe(recipeId: String): Recipe = error("unused")
        override suspend fun getNutritionDisclaimer(): NutritionDisclaimer = error("unused")
    }

    private val remote = FakeDietary()
    private val cache: MealPlanCache = newCache()
    private val repository = CachedDietaryRepository(remote, cache)

    private val offline = ApiException.NetworkError()

    // --- listing ---

    @Test
    fun `online listing is returned and cached for offline use`() = runTest {
        remote.summaries = listOf(summary("p1"), summary("p2", start = "2026-11-01"))
        assertEquals(remote.summaries, repository.getMealPlans())

        remote.failure = offline
        assertEquals(listOf("p2", "p1"), repository.getMealPlans().map { it.id })
    }

    @Test
    fun `offline with an empty cache rethrows instead of returning an empty list`() = runTest {
        remote.failure = offline

        assertFailsWith<ApiException.NetworkError> { repository.getMealPlans() }
        assertFailsWith<ApiException.NetworkError> { repository.getMealPlan("p1") }
    }

    @Test
    fun `an offline error built by the create helper also falls back to the cache`() = runTest {
        remote.summaries = listOf(summary("p1"))
        repository.getMealPlans()

        remote.failure = ApiException.create("offline", ApiException.Code.NETWORK_ERROR)

        assertEquals(listOf("p1"), repository.getMealPlans().map { it.id })
    }

    @Test
    fun `server errors fall back to the cache`() = runTest {
        remote.summaries = listOf(summary("p1"))
        repository.getMealPlans()

        remote.failure = ApiException.HttpError(500, "boom")
        assertEquals(listOf("p1"), repository.getMealPlans().map { it.id })
    }

    @Test
    fun `a rejected session is surfaced, never answered from the cache`() = runTest {
        remote.summaries = listOf(summary("p1"))
        repository.getMealPlans()
        remote.plan = fullPlan("p1")
        repository.getMealPlan("p1")

        // Both shapes the repositories use for a 401: an HttpError, and ApiException.create (a
        // NetworkError by class, with the UNAUTHORIZED code).
        listOf(
            ApiException.HttpError(401, null),
            ApiException.create("Unauthorized", ApiException.Code.UNAUTHORIZED),
        ).forEach { unauthorized ->
            remote.failure = unauthorized
            assertFailsWith<ApiException> { repository.getMealPlans() }
            assertFailsWith<ApiException> { repository.getMealPlan("p1") }
        }
        assertNotNull(cache.getPlan("p1"), "the cache itself is untouched")
    }

    @Test
    fun `other client errors are surfaced too`() = runTest {
        remote.summaries = listOf(summary("p1"))
        repository.getMealPlans()

        listOf(403, 409, 422).forEach { status ->
            remote.failure = ApiException.HttpError(status, null)
            assertFailsWith<ApiException.HttpError>("status $status") { repository.getMealPlans() }
        }
    }

    @Test
    fun `cancellation is never swallowed into a cache fallback`() = runTest {
        remote.summaries = listOf(summary("p1"))
        repository.getMealPlans()

        remote.failure = CancellationException("cancelled")

        assertFailsWith<CancellationException> { repository.getMealPlans() }
        assertFailsWith<CancellationException> { repository.getMealPlan("p1") }
    }

    @Test
    fun `offline listing honours status filter and paging`() = runTest {
        remote.summaries = listOf(
            summary("a", start = "2026-04-01", status = "active"),
            summary("b", start = "2026-03-01", status = "saved"),
            summary("c", start = "2026-02-01", status = "active"),
            summary("d", start = "2026-01-01", status = "active"),
        )
        repository.getMealPlans()
        remote.failure = offline

        assertEquals(listOf("a", "c", "d"), repository.getMealPlans(MealPlanQuery(status = "active")).map { it.id })
        assertEquals(listOf("c"), repository.getMealPlans(MealPlanQuery(status = "active", page = 2, limit = 1)).map { it.id })
        assertEquals(listOf("d"), repository.getMealPlans(MealPlanQuery(status = "active", page = 3, limit = 1)).map { it.id })
    }

    @Test
    fun `the query is passed on to the server`() = runTest {
        val query = MealPlanQuery(status = "saved", page = 2, limit = 5)

        repository.getMealPlans(query)

        assertEquals(query, remote.lastQuery)
    }

    // --- pruning ---

    @Test
    fun `a complete listing prunes plans that were deleted on the server`() = runTest {
        remote.summaries = listOf(summary("keep"), summary("gone"))
        repository.getMealPlans()

        remote.summaries = listOf(summary("keep"))
        repository.getMealPlans()

        assertEquals(listOf("keep"), cache.getPlanIds())
    }

    @Test
    fun `a filtered, later-page or full-page listing never prunes`() = runTest {
        remote.summaries = listOf(summary("a"), summary("b"))
        repository.getMealPlans()

        remote.summaries = listOf(summary("a"))
        repository.getMealPlans(MealPlanQuery(status = "active"))
        assertEquals(setOf("a", "b"), cache.getPlanIds().toSet())

        repository.getMealPlans(MealPlanQuery(page = 2))
        assertEquals(setOf("a", "b"), cache.getPlanIds().toSet())

        // A full page (20 of the default 20) may be a slice of a longer list.
        remote.summaries = List(20) { summary("p$it") }
        repository.getMealPlans()
        assertEquals(true, "b" in cache.getPlanIds())
    }

    // --- cache-first: a cached plan is served, then refreshed from the network ---

    @Test
    fun `a cached plan is served and then refreshed from the network`() = runTest {
        cache.upsertPlan(fullPlan("p1", meals = listOf(meal("m1"))))
        remote.plan = fullPlan("p1", meals = listOf(meal("m1"), meal("m2")))

        val served = repository.getMealPlan("p1")

        assertEquals(listOf("m1"), served.meals.map { it.id })
        assertEquals(listOf("m1", "m2"), cache.getPlan("p1")!!.meals.map { it.id })
    }

    @Test
    fun `a cached plan list is served and then refreshed from the network`() = runTest {
        cache.upsertSummaries(listOf(summary("p1")))
        remote.summaries = listOf(summary("p1"), summary("p2"))

        val served = repository.getMealPlans()

        assertEquals(listOf("p1"), served.map { it.id })
        assertEquals(setOf("p1", "p2"), cache.getPlanIds().toSet())
    }

    // --- detail ---

    @Test
    fun `an opened plan is cached with its detail and available offline`() = runTest {
        remote.plan = fullPlan("p1", meals = listOf(meal("m1")))
        assertEquals(remote.plan, repository.getMealPlan("p1"))

        remote.failure = offline
        assertEquals(remote.plan, repository.getMealPlan("p1"))
    }

    @Test
    fun `a plan only seen in the list has no offline detail`() = runTest {
        remote.summaries = listOf(summary("p1"))
        repository.getMealPlans()

        remote.failure = offline

        assertFailsWith<ApiException.NetworkError> { repository.getMealPlan("p1") }
    }

    @Test
    fun `a 404 evicts the cached plan`() = runTest {
        remote.plan = fullPlan("p1")
        repository.getMealPlan("p1")
        assertNotNull(cache.getPlan("p1"))

        remote.plan = null
        assertFailsWith<ApiException> { repository.getMealPlan("p1") }
        assertNull(cache.getPlan("p1"))
        assertEquals(emptyList(), cache.getPlanIds())

        // The create helper's NOT_FOUND is a NetworkError by class and must evict as well.
        remote.plan = fullPlan("p2")
        repository.getMealPlan("p2")
        remote.failure = ApiException.create("Not found", ApiException.Code.NOT_FOUND)
        assertFailsWith<ApiException> { repository.getMealPlan("p2") }
        assertNull(cache.getPlan("p2"))
    }

    // --- writes ---

    @Test
    fun `a created plan is cached with its detail`() = runTest {
        remote.plan = fullPlan("p1", meals = listOf(meal("m1")))

        repository.createMealPlan(CreateMealPlanRequest("Plan p1", "2026-10-01", "2026-10-07", 2000))

        assertEquals(remote.plan, cache.getPlan("p1"))
    }

    @Test
    fun `a status change updates the cached plan`() = runTest {
        remote.plan = fullPlan("p1")

        repository.updateMealPlanStatus("p1", "completed")

        assertEquals("completed", cache.getPlan("p1")!!.status)
    }

    @Test
    fun `adding a meal forgets the stale detail but keeps the plan listed`() = runTest {
        remote.plan = fullPlan("p1", meals = listOf(meal("m1")))
        repository.getMealPlan("p1")

        repository.addMeal("p1", AddMealRequest(mealType = "lunch", recipeId = "r", servings = 1.0))

        assertNull(cache.getPlan("p1"))
        assertEquals(listOf("p1"), cache.getPlans().map { it.id })
    }

    @Test
    fun `updating a meal forgets the cached plan detail but keeps the plan in the list`() = runTest {
        remote.plan = fullPlan("p1", meals = listOf(meal("m1")))
        repository.getMealPlan("p1")

        repository.updateMeal("p1", "m1", UpdateMealRequest(dayIndex = 2))

        assertNull(cache.getPlan("p1"))
        assertEquals(listOf("p1"), cache.getPlans().map { it.id })
    }

    @Test
    fun `removing a meal forgets the cached plan detail but keeps the plan in the list`() = runTest {
        remote.plan = fullPlan("p1", meals = listOf(meal("m1")))
        repository.getMealPlan("p1")

        repository.removeMeal("p1", "m1")

        assertNull(cache.getPlan("p1"))
        assertEquals(listOf("p1"), cache.getPlans().map { it.id })
    }

    @Test
    fun `a failed removal keeps the cached plan`() = runTest {
        remote.plan = fullPlan("p1", meals = listOf(meal("m1")))
        repository.getMealPlan("p1")
        remote.failure = offline

        assertFailsWith<ApiException.NetworkError> { repository.removeMeal("p1", "m1") }

        assertNotNull(cache.getPlan("p1"))
    }
}