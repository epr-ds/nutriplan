++ b/mobile/shared/src/commonTest/kotlin/com/nutriplan/shared/navigation/RouteDeepLinkTest.kt
package com.nutriplan.shared.navigation

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class RouteDeepLinkTest {

    @Test
    fun `toDeepLink returns correct URI for Splash`() {
        assertEquals("nutriplan://splash", Route.Splash.toDeepLink())
    }

    @Test
    fun `toDeepLink returns correct URI for Onboarding`() {
        assertEquals("nutriplan://onboarding", Route.Onboarding.toDeepLink())
    }

    @Test
    fun `toDeepLink returns correct URI for Auth`() {
        assertEquals("nutriplan://auth", Route.Auth.toDeepLink())
    }

    @Test
    fun `toDeepLink returns correct URI for Main`() {
        assertEquals("nutriplan://main", Route.Main.toDeepLink())
    }

    @Test
    fun `toDeepLink returns correct URI for MealPlanList`() {
        assertEquals("nutriplan://meal-plans", Route.MealPlanList.toDeepLink())
    }

    @Test
    fun `toDeepLink returns correct URI for CreateMealPlan`() {
        assertEquals("nutriplan://meal-plan/new", Route.CreateMealPlan().toDeepLink())
    }

    @Test
    fun `toDeepLink returns correct URI for MealPlanDetail`() {
        val route = Route.MealPlanDetail("plan-123")
        assertEquals("nutriplan://meal-plan/plan-123", route.toDeepLink())
    }

    @Test
    fun `toDeepLink returns correct URI for RecipeSearch`() {
        assertEquals("nutriplan://recipes", Route.RecipeSearch.toDeepLink())
    }

    @Test
    fun `toDeepLink returns correct URI for RecipeDetail`() {
        val route = Route.RecipeDetail("recipe-456")
        assertEquals("nutriplan://recipe/recipe-456", route.toDeepLink())
    }

    @Test
    fun `toDeepLink returns correct URI for AiMealAnalysis`() {
        assertEquals("nutriplan://ai/analyze", Route.AiMealAnalysis.toDeepLink())
    }

    @Test
    fun `toDeepLink returns correct URI for AiRecommendations`() {
        assertEquals("nutriplan://ai/recommend", Route.AiRecommendations.toDeepLink())
    }

    @Test
    fun `toDeepLink returns correct URI for OrderList`() {
        assertEquals("nutriplan://orders", Route.OrderList.toDeepLink())
    }

    @Test
    fun `toDeepLink returns correct URI for OrderDetail`() {
        val route = Route.OrderDetail("order-789")
        assertEquals("nutriplan://order/order-789", route.toDeepLink())
    }

    @Test
    fun `toDeepLink returns correct URI for Checkout`() {
        assertEquals("nutriplan://checkout", Route.Checkout.toDeepLink())
    }

    @Test
    fun `toDeepLink returns correct URI for NotificationCenter`() {
        assertEquals("nutriplan://notifications", Route.NotificationCenter.toDeepLink())
    }

    @Test
    fun `toDeepLink returns correct URI for Profile`() {
        assertEquals("nutriplan://profile", Route.Profile.toDeepLink())
    }

    @Test
    fun `toDeepLink returns correct URI for EditProfile`() {
        assertEquals("nutriplan://profile/edit", Route.EditProfile.toDeepLink())
    }

    @Test
    fun `toDeepLink returns correct URI for DietaryPreferences`() {
        assertEquals("nutriplan://profile/dietary", Route.DietaryPreferences.toDeepLink())
    }

    @Test
    fun `toDeepLink returns correct URI for DeepLinkMeal`() {
        val route = Route.DeepLinkMeal("meal-abc")
        assertEquals("nutriplan://meal/meal-abc", route.toDeepLink())
    }

    @Test
    fun `toDeepLink returns correct URI for DeepLinkPlan`() {
        val route = Route.DeepLinkPlan("plan-def")
        assertEquals("nutriplan://plan/plan-def", route.toDeepLink())
    }

    @Test
    fun `toDeepLink returns correct URI for DeepLinkOrder`() {
        val route = Route.DeepLinkOrder("order-ghi")
        assertEquals("nutriplan://order/order-ghi", route.toDeepLink())
    }

    // fromDeepLink tests

    @Test
    fun `fromDeepLink parses Splash correctly`() {
        assertEquals(Route.Splash, Route.fromDeepLink("nutriplan://splash"))
    }

    @Test
    fun `fromDeepLink parses Onboarding correctly`() {
        assertEquals(Route.Onboarding, Route.fromDeepLink("nutriplan://onboarding"))
    }

    @Test
    fun `fromDeepLink parses Auth correctly`() {
        assertEquals(Route.Auth, Route.fromDeepLink("nutriplan://auth"))
    }

    @Test
    fun `fromDeepLink parses Main correctly`() {
        assertEquals(Route.Main, Route.fromDeepLink("nutriplan://main"))
    }

    @Test
    fun `fromDeepLink parses MealPlanList correctly`() {
        assertEquals(Route.MealPlanList, Route.fromDeepLink("nutriplan://meal-plans"))
    }

    @Test
    fun `fromDeepLink parses CreateMealPlan correctly`() {
        val result = Route.fromDeepLink("nutriplan://meal-plan/new")
        assertEquals(Route.CreateMealPlan(), result)
    }

    @Test
    fun `fromDeepLink parses MealPlanDetail correctly`() {
        val result = Route.fromDeepLink("nutriplan://meal-plan/plan-123")
        assertEquals(Route.MealPlanDetail("plan-123"), result)
    }

    @Test
    fun `fromDeepLink parses RecipeSearch correctly`() {
        assertEquals(Route.RecipeSearch, Route.fromDeepLink("nutriplan://recipes"))
    }

    @Test
    fun `fromDeepLink parses RecipeDetail correctly`() {
        val result = Route.fromDeepLink("nutriplan://recipe/recipe-456")
        assertEquals(Route.RecipeDetail("recipe-456"), result)
    }

    @Test
    fun `fromDeepLink parses AiMealAnalysis correctly`() {
        assertEquals(Route.AiMealAnalysis, Route.fromDeepLink("nutriplan://ai/analyze"))
    }

    @Test
    fun `fromDeepLink parses AiRecommendations correctly`() {
        assertEquals(Route.AiRecommendations, Route.fromDeepLink("nutriplan://ai/recommend"))
    }

    @Test
    fun `fromDeepLink parses OrderList correctly`() {
        assertEquals(Route.OrderList, Route.fromDeepLink("nutriplan://orders"))
    }

    @Test
    fun `fromDeepLink parses OrderDetail correctly`() {
        val result = Route.fromDeepLink("nutriplan://order/order-789")
        assertEquals(Route.OrderDetail("order-789"), result)
    }

    @Test
    fun `fromDeepLink parses Checkout correctly`() {
        assertEquals(Route.Checkout, Route.fromDeepLink("nutriplan://checkout"))
    }

    @Test
    fun `fromDeepLink parses NotificationCenter correctly`() {
        assertEquals(Route.NotificationCenter, Route.fromDeepLink("nutriplan://notifications"))
    }

    @Test
    fun `fromDeepLink parses Profile correctly`() {
        assertEquals(Route.Profile, Route.fromDeepLink("nutriplan://profile"))
    }

    @Test
    fun `fromDeepLink parses EditProfile correctly`() {
        assertEquals(Route.EditProfile, Route.fromDeepLink("nutriplan://profile/edit"))
    }

    @Test
    fun `fromDeepLink parses DietaryPreferences correctly`() {
        assertEquals(Route.DietaryPreferences, Route.fromDeepLink("nutriplan://profile/dietary"))
    }

    @Test
    fun `fromDeepLink parses DeepLinkMeal correctly`() {
        val result = Route.fromDeepLink("nutriplan://meal/meal-abc")
        assertEquals(Route.DeepLinkMeal("meal-abc"), result)
    }

    @Test
    fun `fromDeepLink parses DeepLinkPlan correctly`() {
        val result = Route.fromDeepLink("nutriplan://plan/plan-def")
        assertEquals(Route.DeepLinkPlan("plan-def"), result)
    }

    @Test
    fun `fromDeepLink returns null for unknown deep link`() {
        assertNull(Route.fromDeepLink("nutriplan://unknown"))
    }

    @Test
    fun `fromDeepLink returns null for invalid URL`() {
        assertNull(Route.fromDeepLink("https://example.com"))
    }

    @Test
    fun `fromDeepLink returns null for empty string`() {
        assertNull(Route.fromDeepLink(""))
    }

    @Test
    fun `roundTrip toDeepLink and fromDeepLink preserves Splash`() {
        val deepLink = Route.Splash.toDeepLink()
        assertEquals(Route.Splash, Route.fromDeepLink(deepLink))
    }

    @Test
    fun `roundTrip toDeepLink and fromDeepLink preserves MealPlanDetail`() {
        val route = Route.MealPlanDetail("plan-xyz")
        val deepLink = route.toDeepLink()
        assertEquals(route, Route.fromDeepLink(deepLink))
    }

    @Test
    fun `roundTrip toDeepLink and fromDeepLink preserves OrderDetail`() {
        val route = Route.OrderDetail("order-xyz")
        val deepLink = route.toDeepLink()
        assertEquals(route, Route.fromDeepLink(deepLink))
    }
}
