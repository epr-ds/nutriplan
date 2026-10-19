package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.ApiConfig
import com.nutriplan.shared.data.model.AddMealRequest
import com.nutriplan.shared.data.model.CreateMealPlanRequest
import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.model.MealPlanQuery
import com.nutriplan.shared.data.model.MealPlanSummary
import com.nutriplan.shared.data.model.PlanMeal
import com.nutriplan.shared.data.model.Recipe
import com.nutriplan.shared.data.model.RecipeQuery
import com.nutriplan.shared.data.model.UpdateMealPlanStatusRequest
import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.data.network.HttpClientProvider
import io.ktor.client.call.body
import io.ktor.client.request.get
import io.ktor.client.request.parameter
import io.ktor.client.request.patch
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.client.statement.bodyAsText
import io.ktor.http.isSuccess
import io.ktor.serialization.ContentConvertException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.IO
import kotlinx.coroutines.withContext
import kotlinx.serialization.SerializationException

/**
 * Repository for the Dietary service (`contracts/dietary.openapi.yaml`).
 *
 * Covers meal plans (create, list, get, status change, add meal) and recipe search. Failures are
 * thrown as [ApiException]; use [com.nutriplan.shared.data.network.toApiFailure] to classify them.
 */
interface DietaryRepository {

    /** Create a meal plan (`POST /meal-plans`). It starts as a draft. */
    suspend fun createMealPlan(request: CreateMealPlanRequest): MealPlan

    /** List the caller's meal plans (`GET /meal-plans`); summaries only, 20 per page by default. */
    suspend fun getMealPlans(query: MealPlanQuery? = null): List<MealPlanSummary>

    /** Get a plan with its meals and nutrition (`GET /meal-plans/{planId}`). */
    suspend fun getMealPlan(planId: String): MealPlan

    /**
     * Move a plan through its lifecycle (`PATCH /meal-plans/{planId}`): `active`, `completed` or
     * `saved`. This is the only edit the API offers for a plan itself.
     */
    suspend fun updateMealPlanStatus(planId: String, status: String): MealPlan

    /** Add a meal to a plan (`POST /meal-plans/{planId}/meals`); the response embeds the recipe. */
    suspend fun addMeal(planId: String, request: AddMealRequest): PlanMeal

    /**
     * List recipes with optional filters.
     *
     * Not yet aligned with the contract's `GET /recipes` (query names and the recipe model); that
     * comes with the recipe screens (DPL-405, DPL-601).
     */
    suspend fun getRecipes(query: RecipeQuery? = null): List<Recipe>
}

/**
 * Dietary service API client implementation.
 */
class DietaryRepositoryImpl : DietaryRepository {

    private val client = HttpClientProvider.client

    override suspend fun createMealPlan(request: CreateMealPlanRequest): MealPlan =
        withContext(Dispatchers.IO) {
            client.post("${ApiConfig.DIETARY}/meal-plans") { setBody(request) }.readOrThrow()
        }

    override suspend fun getMealPlans(query: MealPlanQuery?): List<MealPlanSummary> =
        withContext(Dispatchers.IO) {
            client.get("${ApiConfig.DIETARY}/meal-plans") {
                query?.status?.let { parameter("status", it) }
                query?.page?.let { parameter("page", it) }
                query?.limit?.let { parameter("limit", it) }
            }.readOrThrow()
        }

    override suspend fun getMealPlan(planId: String): MealPlan =
        withContext(Dispatchers.IO) {
            client.get("${ApiConfig.DIETARY}/meal-plans/$planId").readOrThrow()
        }

    override suspend fun updateMealPlanStatus(planId: String, status: String): MealPlan =
        withContext(Dispatchers.IO) {
            client.patch("${ApiConfig.DIETARY}/meal-plans/$planId") {
                setBody(UpdateMealPlanStatusRequest(status))
            }.readOrThrow()
        }

    override suspend fun addMeal(planId: String, request: AddMealRequest): PlanMeal =
        withContext(Dispatchers.IO) {
            client.post("${ApiConfig.DIETARY}/meal-plans/$planId/meals") { setBody(request) }.readOrThrow()
        }

    override suspend fun getRecipes(query: RecipeQuery?): List<Recipe> =
        withContext(Dispatchers.IO) {
            client.get("${ApiConfig.DIETARY}/recipes") {
                query?.dietaryPreference?.let { parameter("dietaryPreference", it) }
                query?.calorieRangeMin?.let { parameter("calorieRangeMin", it) }
                query?.calorieRangeMax?.let { parameter("calorieRangeMax", it) }
                query?.limit?.let { parameter("limit", it) }
                query?.offset?.let { parameter("offset", it) }
            }.readOrThrow()
        }

    /**
     * Decodes a 2xx response into [T]; anything else becomes an [ApiException.HttpError] carrying
     * the status and the (problem+json) body, so it classifies by status. A body that does not match
     * the model becomes an [ApiException.SerializationError] instead of an unexplained crash.
     */
    private suspend inline fun <reified T> HttpResponse.readOrThrow(): T {
        if (!status.isSuccess()) {
            throw ApiException.HttpError(statusCode = status.value, body = bodyAsText())
        }
        return try {
            body()
        } catch (e: SerializationException) {
            throw ApiException.SerializationError(errorCause = e)
        } catch (e: ContentConvertException) {
            throw ApiException.SerializationError(errorCause = e)
        }
    }
}
