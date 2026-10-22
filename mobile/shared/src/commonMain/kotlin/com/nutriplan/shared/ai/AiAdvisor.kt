package com.nutriplan.shared.ai

import com.nutriplan.shared.data.model.AiDietaryPreferences
import com.nutriplan.shared.data.model.AiRecommendationRequest
import com.nutriplan.shared.data.model.AiRecommendations
import com.nutriplan.shared.data.model.AnalyzeMealRequest
import com.nutriplan.shared.data.model.DietaryPreferences
import com.nutriplan.shared.data.model.MealAnalysis
import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.model.OptimizePlanRequest
import com.nutriplan.shared.data.network.ApiFailure
import com.nutriplan.shared.data.network.isResponseTimeout
import com.nutriplan.shared.data.network.toApiFailure
import com.nutriplan.shared.data.repository.AiRepository
import kotlin.coroutines.cancellation.CancellationException

/** Why an AI request did not give a result. Locale-neutral: each platform maps these to its own copy. */
enum class AiError {
    /** The device could not reach the server. */
    NETWORK,

    /** The server was reached but took too long to answer, as AI answers sometimes do (AIA-606). */
    TIMEOUT,

    /** The server failed (HTTP 5xx), for example the AI model is unavailable. */
    SERVER_PROBLEM,

    /** The server rejected the session (HTTP 401): the user has to sign in again. */
    SESSION_EXPIRED,

    /** The plan does not exist (any more) or is not the caller's. */
    NOT_FOUND,

    /** The request was refused (HTTP 400/422), or was empty before it was even sent. */
    REJECTED,

    /** Anything else. */
    UNKNOWN,
}

/** The typed result of an AI request: a value, or why there is none. */
sealed interface AiResult<out T> {
    data class Success<out T>(val value: T) : AiResult<T>
    data class Failure(val error: AiError) : AiResult<Nothing>
}

/** Maps a thrown repository failure to a stable, localizable [AiError]; a slow answer is not "offline". */
fun Throwable.toAiError(): AiError {
    if (isResponseTimeout()) return AiError.TIMEOUT
    return when (toApiFailure()) {
        ApiFailure.OFFLINE -> AiError.NETWORK
        ApiFailure.SERVER -> AiError.SERVER_PROBLEM
        ApiFailure.SESSION_EXPIRED -> AiError.SESSION_EXPIRED
        ApiFailure.NOT_FOUND -> AiError.NOT_FOUND
        ApiFailure.REJECTED -> AiError.REJECTED
        else -> AiError.UNKNOWN
    }
}

/**
 * The AI Advisor use cases (AIA-601), shared by the Compose and SwiftUI screens: recipe
 * recommendations, meal analysis and plan optimization, each returning an [AiResult] instead of
 * throwing, so a screen only has to handle a value or an [AiError].
 *
 * Every AI response carries a medical disclaimer (AIA-505) that the screens must show with it.
 *
 * @param language the user's language (`es` or `en`, from the platform); the AI service writes its
 *   reasoning and disclaimer in it. Anything else falls back to Spanish, the contract's default.
 */
class AiAdvisor(
    private val repository: AiRepository,
    private val language: () -> String = { DEFAULT_LANGUAGE },
) {

    /**
     * Recipes recommended for the user. The kind of recommendation follows what was given: ingredients
     * on hand make it ingredient-based, a meal type makes it a single meal, and otherwise it is for a
     * whole meal plan. The calorie target defaults to the one in [preferences].
     */
    suspend fun recommend(
        preferences: DietaryPreferences?,
        mealType: String? = null,
        availableIngredients: List<String> = emptyList(),
        calorieTarget: Int? = null,
    ): AiResult<AiRecommendations> {
        val ingredients = availableIngredients.map(String::trim).filter(String::isNotEmpty).distinct()
        val request = AiRecommendationRequest(
            context = when {
                ingredients.isNotEmpty() -> CONTEXT_INGREDIENTS
                mealType != null -> CONTEXT_SINGLE_MEAL
                else -> CONTEXT_MEAL_PLAN
            },
            dietaryPreferences = preferences?.toAi(),
            availableIngredients = ingredients.ifEmpty { null },
            mealType = mealType,
            calorieTarget = calorieTarget ?: preferences?.dailyCalorieTarget,
            language = supportedLanguage(),
        )
        return call { repository.recommendations(request) }
    }

    /** The estimated nutrition of a meal described in words. A blank description is not sent. */
    suspend fun analyzeMeal(description: String): AiResult<MealAnalysis> {
        val text = description.trim()
        if (text.isEmpty()) return AiResult.Failure(AiError.REJECTED)
        return call { repository.analyzeMeal(AnalyzeMealRequest(description = text)) }
    }

    /** An optimized draft of the plan toward [goal]; the stored plan is not changed. */
    suspend fun optimizePlan(planId: String, goal: String? = null): AiResult<MealPlan> =
        call { repository.optimizePlan(OptimizePlanRequest(planId = planId, goal = goal)) }

    private suspend fun <T> call(block: suspend () -> T): AiResult<T> =
        try {
            AiResult.Success(block())
        } catch (e: CancellationException) {
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            AiResult.Failure(e.toAiError())
        }

    private fun supportedLanguage(): String =
        language().lowercase().take(2).takeIf { it in SUPPORTED_LANGUAGES } ?: DEFAULT_LANGUAGE

    private fun DietaryPreferences.toAi() = AiDietaryPreferences(
        dietType = dietType,
        allergies = allergies?.takeIf { it.isNotEmpty() },
        dailyCalorieTarget = dailyCalorieTarget,
        macroTargets = macroTargets,
        excludedIngredients = excludedIngredients?.takeIf { it.isNotEmpty() },
        cuisinePreferences = cuisinePreferences?.takeIf { it.isNotEmpty() },
    )

    companion object {
        const val CONTEXT_MEAL_PLAN = "meal_plan"
        const val CONTEXT_SINGLE_MEAL = "single_meal"
        const val CONTEXT_INGREDIENTS = "ingredient_based"

        /** The goals a plan can be optimized toward (`OptimizePlanRequest.goal`). */
        val GOALS = listOf("balance_macros", "increase_protein", "reduce_calories", "increase_satisfaction")

        private const val DEFAULT_LANGUAGE = "es"
        private val SUPPORTED_LANGUAGES = setOf("es", "en")
    }
}
