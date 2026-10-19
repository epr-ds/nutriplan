package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.local.MealPlanCache
import com.nutriplan.shared.data.model.AddMealRequest
import com.nutriplan.shared.data.model.UpdateMealRequest
import com.nutriplan.shared.data.model.CreateMealPlanRequest
import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.model.MealPlanQuery
import com.nutriplan.shared.data.model.MealPlanSummary
import com.nutriplan.shared.data.model.PlanMeal
import com.nutriplan.shared.data.network.ApiFailure
import com.nutriplan.shared.data.network.toApiFailure
import kotlin.coroutines.cancellation.CancellationException

/**
 * [DietaryRepository] that keeps meal plans in a local [MealPlanCache] and serves them when the
 * server cannot be reached.
 *
 * - Successful reads and writes refresh the cache.
 * - The cache is used only when the device is offline or the server answers with a 5xx error
 *   (see [ApiFailure]). A rejected session (401) is surfaced, never answered from the cache, and a
 *   404 evicts the cached plan.
 * - If nothing is cached, the original error is rethrown, so a screen shows an error instead of an
 *   empty list.
 * - Offline writes are not supported: create, status change and add-meal need the server.
 */
class CachedDietaryRepository(
    private val remote: DietaryRepository,
    private val cache: MealPlanCache,
) : DietaryRepository by remote {

    override suspend fun getMealPlans(query: MealPlanQuery?): List<MealPlanSummary> {
        val plans = try {
            remote.getMealPlans(query)
        } catch (e: CancellationException) {
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            if (!e.canFallBackToCache()) throw e
            val cached = cachedPlans(query)
            if (cached.isEmpty()) throw e
            return cached
        }
        cache.upsertSummaries(plans)
        if (query.coversEveryPlan(plans.size)) pruneRemoved(plans)
        return plans
    }

    override suspend fun getMealPlan(planId: String): MealPlan =
        try {
            remote.getMealPlan(planId).also(cache::upsertPlan)
        } catch (e: CancellationException) {
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            when {
                e.toApiFailure() == ApiFailure.NOT_FOUND -> {
                    cache.delete(planId)
                    throw e
                }
                e.canFallBackToCache() -> cache.getPlan(planId) ?: throw e
                else -> throw e
            }
        }

    override suspend fun createMealPlan(request: CreateMealPlanRequest): MealPlan =
        remote.createMealPlan(request).also(cache::upsertPlan)

    override suspend fun updateMealPlanStatus(planId: String, status: String): MealPlan =
        remote.updateMealPlanStatus(planId, status).also(cache::upsertPlan)

    override suspend fun addMeal(planId: String, request: AddMealRequest): PlanMeal =
        // The cached detail is stale after this; forget it so the next online read refills it.
        remote.addMeal(planId, request).also { cache.invalidateDetail(planId) }

    override suspend fun updateMeal(planId: String, mealId: String, request: UpdateMealRequest): PlanMeal =
        remote.updateMeal(planId, mealId, request).also { cache.invalidateDetail(planId) }

    override suspend fun removeMeal(planId: String, mealId: String) {
        remote.removeMeal(planId, mealId)
        cache.invalidateDetail(planId)
    }

    /** After a listing that returned every plan, drop cached plans that no longer exist on the server. */
    private fun pruneRemoved(serverPlans: List<MealPlanSummary>) {
        val onServer = serverPlans.map { it.id }.toSet()
        cache.getPlanIds().filter { it !in onServer }.forEach(cache::delete)
    }

    private fun cachedPlans(query: MealPlanQuery?): List<MealPlanSummary> {
        val filtered = cache.getPlans().filter { query?.status == null || it.status == query.status }
        val limit = query?.limit ?: DEFAULT_PAGE_SIZE
        val page = (query?.page ?: 1).coerceAtLeast(1)
        return filtered.drop((page - 1) * limit).take(limit)
    }

    /**
     * Whether a listing with this query and [returned] count held *all* of the user's plans: no
     * status filter, the first page, and a page that was not full. Anything else may be a slice, and
     * pruning from a slice would delete plans that still exist.
     */
    private fun MealPlanQuery?.coversEveryPlan(returned: Int): Boolean =
        (this?.status == null) && ((this?.page ?: 1) == 1) && returned < (this?.limit ?: DEFAULT_PAGE_SIZE)

    private fun Throwable.canFallBackToCache(): Boolean =
        toApiFailure().let { it == ApiFailure.OFFLINE || it == ApiFailure.SERVER }

    private companion object {
        /** The server's default page size for `GET /meal-plans`. */
        const val DEFAULT_PAGE_SIZE = 20
    }
}
