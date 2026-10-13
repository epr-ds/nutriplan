package com.nutriplan.shared.navigation

import kotlinx.serialization.Serializable

/**
 * Typed navigation routes for the app.
 *
 * All routes are defined here to ensure type safety across the navigation graph.
 * Routes are [Serializable] so navigation-compose can build type-safe destinations from them.
 */
@Serializable
sealed class Route {

    /** Splash screen. */
    @Serializable
    object Splash : Route()

    /** Onboarding flow (first-time user). */
    @Serializable
    object Onboarding : Route()

    /** Auth flow (login/register). */
    @Serializable
    object Auth : Route()

    /** Main app bottom nav. */
    @Serializable
    object Main : Route()

    // --- Meal Plan screens ---
    /** Meal plan list. */
    @Serializable
    object MealPlanList : Route()

    /** Create/edit meal plan. */
    @Serializable
    data class CreateMealPlan(val planId: String? = null) : Route()

    /** View meal plan detail. */
    @Serializable
    data class MealPlanDetail(val planId: String) : Route()

    // --- Recipe screens ---
    /** Recipe search. */
    @Serializable
    object RecipeSearch : Route()

    /** Recipe detail. */
    @Serializable
    data class RecipeDetail(val recipeId: String) : Route()

    // --- AI screens ---
    /** AI meal analysis. */
    @Serializable
    object AiMealAnalysis : Route()

    /** AI recommendations. */
    @Serializable
    object AiRecommendations : Route()

    // --- Commerce screens ---
    /** Order list. */
    @Serializable
    object OrderList : Route()

    /** Order detail. */
    @Serializable
    data class OrderDetail(val orderId: String) : Route()

    /** Checkout flow. */
    @Serializable
    object Checkout : Route()

    // --- Notification screens ---
    /** Notification center. */
    @Serializable
    object NotificationCenter : Route()

    // --- Profile screens ---
    /** User profile. */
    @Serializable
    object Profile : Route()

    /** Edit profile. */
    @Serializable
    object EditProfile : Route()

    /** Dietary preferences. */
    @Serializable
    object DietaryPreferences : Route()

    // --- Deep links ---
    /** Deep link to a meal. */
    @Serializable
    data class DeepLinkMeal(val mealId: String) : Route()

    /** Deep link to a plan. */
    @Serializable
    data class DeepLinkPlan(val planId: String) : Route()

    /** Deep link to an order. */
    @Serializable
    data class DeepLinkOrder(val orderId: String) : Route()

    /** Convert route to a string for deep linking. */
    fun toDeepLink(): String = when (this) {
        is Splash -> "nutriplan://splash"
        is Onboarding -> "nutriplan://onboarding"
        is Auth -> "nutriplan://auth"
        is Main -> "nutriplan://main"
        is MealPlanList -> "nutriplan://meal-plans"
        is CreateMealPlan -> "nutriplan://meal-plan/${planId ?: "new"}"
        is MealPlanDetail -> "nutriplan://meal-plan/$planId"
        is RecipeSearch -> "nutriplan://recipes"
        is RecipeDetail -> "nutriplan://recipe/$recipeId"
        is AiMealAnalysis -> "nutriplan://ai/analyze"
        is AiRecommendations -> "nutriplan://ai/recommend"
        is OrderList -> "nutriplan://orders"
        is OrderDetail -> "nutriplan://order/$orderId"
        is Checkout -> "nutriplan://checkout"
        is NotificationCenter -> "nutriplan://notifications"
        is Profile -> "nutriplan://profile"
        is EditProfile -> "nutriplan://profile/edit"
        is DietaryPreferences -> "nutriplan://profile/dietary"
        is DeepLinkMeal -> "nutriplan://meal/$mealId"
        is DeepLinkPlan -> "nutriplan://plan/$planId"
        is DeepLinkOrder -> "nutriplan://order/$orderId"
    }

    companion object {
        /** Parse a deep link string back to a Route. */
        fun fromDeepLink(deepLink: String): Route? = when {
            deepLink == "nutriplan://splash" -> Splash
            deepLink == "nutriplan://onboarding" -> Onboarding
            deepLink == "nutriplan://auth" -> Auth
            deepLink == "nutriplan://main" -> Main
            deepLink == "nutriplan://meal-plans" -> MealPlanList
            deepLink.startsWith("nutriplan://meal-plan/") -> {
                val id = deepLink.substringAfter("nutriplan://meal-plan/")
                if (id == "new") CreateMealPlan() else MealPlanDetail(id)
            }
            deepLink == "nutriplan://recipes" -> RecipeSearch
            deepLink.startsWith("nutriplan://recipe/") -> RecipeDetail(deepLink.substringAfter("nutriplan://recipe/"))
            deepLink == "nutriplan://ai/analyze" -> AiMealAnalysis
            deepLink == "nutriplan://ai/recommend" -> AiRecommendations
            deepLink == "nutriplan://orders" -> OrderList
            deepLink.startsWith("nutriplan://order/") -> OrderDetail(deepLink.substringAfter("nutriplan://order/"))
            deepLink == "nutriplan://checkout" -> Checkout
            deepLink == "nutriplan://notifications" -> NotificationCenter
            deepLink == "nutriplan://profile" -> Profile
            deepLink == "nutriplan://profile/edit" -> EditProfile
            deepLink == "nutriplan://profile/dietary" -> DietaryPreferences
            deepLink.startsWith("nutriplan://meal/") -> DeepLinkMeal(deepLink.substringAfter("nutriplan://meal/"))
            deepLink.startsWith("nutriplan://plan/") -> DeepLinkPlan(deepLink.substringAfter("nutriplan://plan/"))
            else -> null
        }
    }
}
