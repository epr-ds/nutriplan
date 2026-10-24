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

    /** Post-signup onboarding wizard (diet, allergies, targets). */
    @Serializable
    object OnboardingWizard : Route()

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

    /**
     * Choose a recipe to add to the plan [planId] (recipe search in picking mode). In-app only: it
     * has no deep link that opens it from outside.
     */
    @Serializable
    data class PickRecipe(val planId: String) : Route()

    /**
     * Add [recipeId] to the plan [planId] as a meal (meal type, servings, day), with [mealType]
     * already chosen when known (an AI recommendation for one meal). In-app only.
     */
    @Serializable
    data class AddMeal(val planId: String, val recipeId: String, val mealType: String? = null) : Route()

    /**
     * Choose the plan to add [recipeId] to (an AI recommendation, AIA-604), then continue to
     * [AddMeal] with [mealType]. In-app only: it has no deep link that opens it from outside.
     */
    @Serializable
    data class PickPlan(val recipeId: String, val mealType: String? = null) : Route()

    /**
     * Optimize the plan [planId] with the AI Advisor: pick a goal, review the changes, accept or
     * discard (AIA-605). In-app only.
     */
    @Serializable
    data class OptimizePlan(val planId: String) : Route()

    /** Edit, rate or remove the meal [mealId] of the plan [planId]. In-app only. */
    @Serializable
    data class EditMeal(val planId: String, val mealId: String) : Route()

    // --- Recipe screens ---
    /** Recipe search. */
    @Serializable
    object RecipeSearch : Route()

    /** The recipes the user saved as favorites. */
    @Serializable
    object FavoriteRecipes : Route()

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

    /**
     * Checkout flow (COM-605), optionally for one meal plan, or repeating the delivery of order
     * [reorderOrderId] (COM-701). A reorder is started from the order list, not from a deep link.
     */
    @Serializable
    data class Checkout(val planId: String? = null, val reorderOrderId: String? = null) : Route()

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

    /** The user's delivery addresses (COM-601). */
    @Serializable
    object AddressBook : Route()

    /** The user's saved payment methods (COM-603). */
    @Serializable
    object PaymentMethods : Route()

    // --- Deep links ---
    /** Deep link to a meal. */
    @Serializable
    data class DeepLinkMeal(val mealId: String) : Route()

    /**
     * Deep link to a plan, optionally with an action sub-path such as `manage`, `summary` or
     * `renew` (`nutriplan://plan/<id>/<action>`, as sent by plan-ending notifications).
     */
    @Serializable
    data class DeepLinkPlan(val planId: String, val action: String? = null) : Route()

    /** Deep link to an order. */
    @Serializable
    data class DeepLinkOrder(val orderId: String) : Route()

    /** Convert route to a string for deep linking. */
    fun toDeepLink(): String = when (this) {
        is Splash -> "nutriplan://splash"
        is Onboarding -> "nutriplan://onboarding"
        is OnboardingWizard -> "nutriplan://onboarding/wizard"
        is Auth -> "nutriplan://auth"
        is Main -> "nutriplan://main"
        is MealPlanList -> "nutriplan://meal-plans"
        is CreateMealPlan -> "nutriplan://meal-plan/${planId ?: "new"}"
        is MealPlanDetail -> "nutriplan://meal-plan/$planId"
        is PickRecipe -> "nutriplan://add-meal/$planId"
        is AddMeal -> "nutriplan://add-meal/$planId/$recipeId"
        is PickPlan -> "nutriplan://add-to-plan/$recipeId"
        is OptimizePlan -> "nutriplan://optimize-plan/$planId"
        is EditMeal -> "nutriplan://edit-meal/$planId/$mealId"
        is FavoriteRecipes -> "nutriplan://recipes/favorites"
        is RecipeSearch -> "nutriplan://recipes"
        is RecipeDetail -> "nutriplan://recipe/$recipeId"
        is AiMealAnalysis -> "nutriplan://ai/analyze"
        is AiRecommendations -> "nutriplan://ai/recommend"
        is OrderList -> "nutriplan://orders"
        is OrderDetail -> "nutriplan://order/$orderId"
        is Checkout -> "nutriplan://checkout" + (planId?.let { "/$it" } ?: "")
        is NotificationCenter -> "nutriplan://notifications"
        is Profile -> "nutriplan://profile"
        is EditProfile -> "nutriplan://profile/edit"
        is DietaryPreferences -> "nutriplan://profile/dietary"
        is AddressBook -> "nutriplan://profile/addresses"
        is PaymentMethods -> "nutriplan://profile/payment-methods"
        is DeepLinkMeal -> "nutriplan://meal/$mealId"
        is DeepLinkPlan -> "nutriplan://plan/$planId" + (action?.let { "/$it" } ?: "")
        is DeepLinkOrder -> "nutriplan://order/$orderId"
    }

    companion object {
        /** Parse a deep link string back to a Route. */
        fun fromDeepLink(deepLink: String): Route? = when {
            deepLink == "nutriplan://splash" -> Splash
            deepLink == "nutriplan://onboarding" -> Onboarding
            deepLink == "nutriplan://onboarding/wizard" -> OnboardingWizard
            deepLink == "nutriplan://auth" -> Auth
            deepLink == "nutriplan://main" -> Main
            deepLink == "nutriplan://meal-plans" -> MealPlanList
            deepLink.startsWith("nutriplan://meal-plan/") -> {
                val id = deepLink.substringAfter("nutriplan://meal-plan/")
                if (id == "new") CreateMealPlan() else MealPlanDetail(id)
            }
            deepLink == "nutriplan://recipes" -> RecipeSearch
            deepLink == "nutriplan://recipes/favorites" -> FavoriteRecipes
            deepLink.startsWith("nutriplan://recipe/") -> RecipeDetail(deepLink.substringAfter("nutriplan://recipe/"))
            deepLink == "nutriplan://ai/analyze" -> AiMealAnalysis
            deepLink == "nutriplan://ai/recommend" -> AiRecommendations
            deepLink == "nutriplan://orders" -> OrderList
            deepLink.startsWith("nutriplan://order/") -> OrderDetail(deepLink.substringAfter("nutriplan://order/"))
            deepLink == "nutriplan://checkout" -> Checkout()
            deepLink.startsWith("nutriplan://checkout/") -> Checkout(deepLink.substringAfter("nutriplan://checkout/"))
            deepLink == "nutriplan://notifications" -> NotificationCenter
            deepLink == "nutriplan://profile" -> Profile
            deepLink == "nutriplan://profile/edit" -> EditProfile
            deepLink == "nutriplan://profile/dietary" -> DietaryPreferences
            deepLink == "nutriplan://profile/addresses" -> AddressBook
            deepLink == "nutriplan://profile/payment-methods" -> PaymentMethods
            deepLink.startsWith("nutriplan://meal/") -> DeepLinkMeal(deepLink.substringAfter("nutriplan://meal/"))
            deepLink.startsWith("nutriplan://plan/") -> parsePlanLink(deepLink.substringAfter("nutriplan://plan/"))
            else -> null
        }

        /**
         * Resolve the route a push notification should open from its data payload.
         *
         * The notification service puts the target in the `deepLink` field
         * (for example `nutriplan://meal/<id>` or `nutriplan://plan/<id>/manage`).
         */
        fun fromNotificationData(data: Map<String, String>): Route? =
            data[NOTIFICATION_DEEP_LINK_KEY]?.let(::fromDeepLink)

        private const val NOTIFICATION_DEEP_LINK_KEY = "deepLink"

        /** Parse `<planId>` or `<planId>/<action>`; anything else (blank id, extra segments) is rejected. */
        private fun parsePlanLink(path: String): Route? {
            val segments = path.split("/")
            val planId = segments.first()
            return when {
                planId.isBlank() -> null
                segments.size == 1 -> DeepLinkPlan(planId)
                segments.size == 2 && segments[1].isNotBlank() -> DeepLinkPlan(planId, segments[1])
                else -> null
            }
        }
    }
}
