++ b/mobile/shared/src/commonMain/kotlin/com/nutriplan/shared/data/repository/DietaryRepository.kt
package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.ApiConfig
import com.nutriplan.shared.data.model.AddMealRequest
import com.nutriplan.shared.data.model.CreateMealPlanRequest
import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.model.MealPlanQuery
import com.nutriplan.shared.data.model.Recipe
import com.nutriplan.shared.data.model.RecipeQuery
import com.nutriplan.shared.data.model.UpdateMealPlanRequest
import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.data.network.HttpClientProvider
import io.ktor.client.call.body
import io.ktor.client.request.get
import io.ktor.client.request.patch
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.HttpStatusCode
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.IO
import kotlinx.coroutines.withContext

/**
 * Repository for dietary-related API operations.
 *
 * Covers meal plan CRUD, meal additions, and recipe queries.
 */
interface DietaryRepository {

    /** Create a new meal plan. */
    suspend fun createMealPlan(request: CreateMealPlanRequest): MealPlan

    /** List meal plans with optional filters. */
    suspend fun getMealPlans(query: MealPlanQuery? = null): List<MealPlan>

    /** Get a specific meal plan by ID. */
    suspend fun getMealPlan(planId: String): MealPlan

    /** Update an existing meal plan. */
    suspend fun updateMealPlan(planId: String, request: UpdateMealPlanRequest): MealPlan

    /** Add a meal to a plan. */
    suspend fun addMeal(planId: String, request: AddMealRequest): Any

    /** List recipes with optional filters. */
    suspend fun getRecipes(query: RecipeQuery? = null): List<Recipe>
}

/**
 * Dietary service API client implementation.
 */
class DietaryRepositoryImpl : DietaryRepository {

    private val client = HttpClientProvider.client

    override suspend fun createMealPlan(request: CreateMealPlanRequest): MealPlan {
        return withContext(Dispatchers.IO) {
            val response = client.post("${ApiConfig.DIETARY}/meal-plans") {
                setBody(request)
            }
            handleResponse(response)
        }
    }

    override suspend fun getMealPlans(query: MealPlanQuery?): List<MealPlan> {
        return withContext(Dispatchers.IO) {
            val queryParams = mutableListOf<String>()
            query?.let { q ->
                q.status?.let { queryParams.add("status=$it") }
                q.limit?.let { queryParams.add("limit=$it") }
                q.offset?.let { queryParams.add("offset=$it") }
            }
            val url = if (queryParams.isEmpty()) {
                "${ApiConfig.DIETARY}/meal-plans"
            } else {
                "${ApiConfig.DIETARY}/meal-plans?${queryParams.joinToString("&")}"
            }
            val response = client.get(url)
            handleListResponse<MealPlan>(response)
        }
    }

    override suspend fun getMealPlan(planId: String): MealPlan {
        return withContext(Dispatchers.IO) {
            val response = client.get("${ApiConfig.DIETARY}/meal-plans/$planId")
            handleResponse(response)
        }
    }

    override suspend fun updateMealPlan(planId: String, request: UpdateMealPlanRequest): MealPlan {
        return withContext(Dispatchers.IO) {
            val response = client.patch("${ApiConfig.DIETARY}/meal-plans/$planId") {
                setBody(request)
            }
            handleResponse(response)
        }
    }

    override suspend fun addMeal(planId: String, request: AddMealRequest): Any {
        return withContext(Dispatchers.IO) {
            val response = client.post("${ApiConfig.DIETARY}/meal-plans/$planId/meals") {
                setBody(request)
            }
            @Suppress("UNCHECKED_CAST")
            response.body() as Any
        }
    }

    override suspend fun getRecipes(query: RecipeQuery?): List<Recipe> {
        return withContext(Dispatchers.IO) {
            val queryParams = mutableListOf<String>()
            query?.let { q ->
                q.dietaryPreference?.let { queryParams.add("dietaryPreference=$it") }
                q.calorieRangeMin?.let { queryParams.add("calorieRangeMin=$it") }
                q.calorieRangeMax?.let { queryParams.add("calorieRangeMax=$it") }
                q.limit?.let { queryParams.add("limit=$it") }
                q.offset?.let { queryParams.add("offset=$it") }
            }
            val url = if (queryParams.isEmpty()) {
                "${ApiConfig.DIETARY}/recipes"
            } else {
                "${ApiConfig.DIETARY}/recipes?${queryParams.joinToString("&")}"
            }
            val response = client.get(url)
            handleListResponse<Recipe>(response)
        }
    }

    private suspend inline fun <reified T> handleResponse(response: io.ktor.client.statement.HttpResponse): T {
        return when (response.status) {
            HttpStatusCode.OK, HttpStatusCode.Created -> response.body()
            HttpStatusCode.Unauthorized -> throw ApiException.create(
                message = "Unauthorized. Please log in again.",
                code = ApiException.Code.UNAUTHORIZED,
            )
            HttpStatusCode.Forbidden -> throw ApiException.create(
                message = "Forbidden. You don't have permission.",
                code = ApiException.Code.FORBIDDEN,
            )
            HttpStatusCode.NotFound -> throw ApiException.create(
                message = "Resource not found.",
                code = ApiException.Code.NOT_FOUND,
            )
            else -> throw ApiException.HttpError(
                statusCode = response.status.value,
                body = response.body<String>(),
            )
        }
    }

    private suspend inline fun <reified T> handleListResponse(response: io.ktor.client.statement.HttpResponse): List<T> {
        return when (response.status) {
            HttpStatusCode.OK -> response.body()
            HttpStatusCode.Unauthorized -> throw ApiException.create(
                message = "Unauthorized. Please log in again.",
                code = ApiException.Code.UNAUTHORIZED,
            )
            else -> throw ApiException.HttpError(
                statusCode = response.status.value,
                body = response.body<String>(),
            )
        }
    }
}
