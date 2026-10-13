package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.local.MealPlanCache
import com.nutriplan.shared.data.model.AddMealRequest
import com.nutriplan.shared.data.model.CreateMealPlanRequest
import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.model.MealPlanQuery
import com.nutriplan.shared.data.model.UpdateMealPlanRequest
import com.nutriplan.shared.data.network.ApiException

/**
 * [DietaryRepository] that keeps meal plans in a local [MealPlanCache] and serves them when
 * the server cannot be reached.
 *
 * - Successful reads and writes refresh the cache.
 * - The cache is used only when the server is unreachable or answers with a 5xx error. Auth
 *   and permission errors (401/403) are surfaced, and a 404 evicts the cached plan.
 * - If nothing is cached, the original error is rethrown, so a screen shows an error instead
 *   of an empty list.
 * - Offline writes are not supported: create, update and add-meal need the server.
 */
class CachedDietaryRepository(
    private val remote: DietaryRepository,
    private val cache: MealPlanCache,
) : DietaryRepository by remote {

    override suspend fun getMealPlans(query: MealPlanQuery?): List<MealPlan> {
        val plans = try {
            remote.getMealPlans(query)
        } catch (e: ApiException) {
            if (!e.isUnreachable()) throw e
            val cached = cachedPlans(query)
            if (cached.isEmpty()) throw e
            return cached
        }
        plans.forEach(::store)
        if (query.isUnfiltered()) pruneRemoved(plans)
        return plans
    }

    override suspend fun getMealPlan(planId: String): MealPlan =
        try {
            remote.getMealPlan(planId).also(::store)
        } catch (e: ApiException) {
            when {
                e.code == ApiException.Code.NOT_FOUND -> {
                    cache.delete(planId)
                    throw e
                }
                e.isUnreachable() -> cache.getPlan(planId) ?: throw e
                else -> throw e
            }
        }

    override suspend fun createMealPlan(request: CreateMealPlanRequest): MealPlan =
        remote.createMealPlan(request).also(::store)

    override suspend fun updateMealPlan(planId: String, request: UpdateMealPlanRequest): MealPlan =
        remote.updateMealPlan(planId, request).also(::store)

    override suspend fun addMeal(planId: String, request: AddMealRequest): Any =
        // The cached meals are stale after this; drop the plan so the next online read refills it.
        remote.addMeal(planId, request).also { cache.delete(planId) }

    /** Cache a plan from the server, keeping cached meals if the response omitted them. */
    private fun store(plan: MealPlan) {
        val meals = plan.meals ?: cache.getPlan(plan.id)?.meals
        cache.upsert(plan.copy(meals = meals), synced = true)
    }

    /** After a full listing, drop cached plans that no longer exist on the server. */
    private fun pruneRemoved(serverPlans: List<MealPlan>) {
        val onServer = serverPlans.map { it.id }.toSet()
        cache.getSyncedPlanIds().filter { it !in onServer }.forEach(cache::delete)
    }

    private fun cachedPlans(query: MealPlanQuery?): List<MealPlan> {
        val filtered = cache.getPlans().filter { query?.status == null || it.status == query.status }
        val paged = filtered.drop(query?.offset ?: 0)
        return query?.limit?.let(paged::take) ?: paged
    }

    private fun MealPlanQuery?.isUnfiltered(): Boolean =
        this == null || (status == null && limit == null && offset == null)

    private fun ApiException.isUnreachable(): Boolean =
        this is ApiException.NetworkError || code == ApiException.Code.SERVER_ERROR
}
