package com.nutriplan.android.navigation

import androidx.lifecycle.SavedStateHandle
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.toRoute
import com.nutriplan.shared.analytics.AnalyticsTracker
import com.nutriplan.shared.domain.Resource
import com.nutriplan.shared.navigation.Route

/**
 * Top-level navigation graph for the NutriPlan app.
 *
 * Routes are typed via [Route] objects for compile-time safety.
 * Screen composable functions are passed in as parameters to keep
 * this file focused on navigation wiring.
 *
 * HRD-606: Logs screen views and key funnel events to Firebase Analytics.
 */
@Composable
fun AppNavigationGraph(
    navController: NavHostController,
    startDestination: Any = Route.Splash,
    onAuthStateChanged: (Boolean) -> Unit = {},
    onDeepLink: (String) -> Unit = {},
    analyticsTracker: AnalyticsTracker? = null,
    screens: AppNavigationScreens,
) {
    NavHost(
        navController = navController,
        startDestination = startDestination,
    ) {
        // Splash screen
        composable<Route.Splash> {
            analyticsTracker?.logScreenView("splash", "SplashScreen")
            screens.SplashScreen(
                // The splash screen must not stay in the back stack, or Back would return to it.
                onNavigate = { route ->
                    navController.navigate(route) { popUpTo<Route.Splash> { inclusive = true } }
                },
            )
        }

        // Onboarding (first-run intro)
        composable<Route.Onboarding> {
            analyticsTracker?.logScreenView("onboarding", "OnboardingScreen")
            screens.OnboardingScreen(
                onComplete = { route ->
                    analyticsTracker?.logEvent("onboarding_complete", emptyMap())
                    navigate(navController, route)
                },
            )
        }

        // Onboarding wizard (post-signup: diet, allergies, targets)
        composable<Route.OnboardingWizard> {
            analyticsTracker?.logScreenView("onboarding_wizard", "OnboardingWizardScreen")
            screens.OnboardingWizardScreen(
                onComplete = { route ->
                    analyticsTracker?.logEvent("onboarding_complete", emptyMap())
                    analyticsTracker?.setUserProperty("activated", "true")
                    // The wizard is the last step of signup; Back must not return to it.
                    navController.navigate(route) { popUpTo<Route.OnboardingWizard> { inclusive = true } }
                },
            )
        }

        // Auth
        composable<Route.Auth> {
            analyticsTracker?.logScreenView("auth", "AuthScreen")
            screens.AuthScreen(
                // After signing in, Back must not return to the login screen.
                onLoginSuccess = { route ->
                    analyticsTracker?.logEvent("login_success", emptyMap())
                    analyticsTracker?.setUserProperty("auth_status", "authenticated")
                    navController.navigate(route) { popUpTo<Route.Auth> { inclusive = true } }
                },
            )
        }

        // Main app
        composable<Route.Main> {
            analyticsTracker?.logScreenView("main", "MainScreen")
            screens.MainScreen(
                onNavigate = { route -> navigate(navController, route) },
            )
        }

        // Meal plan list
        composable<Route.MealPlanList> {
            analyticsTracker?.logScreenView("meal_plan_list", "MealPlanListScreen")
            screens.MealPlanListScreen(
                onNavigate = { route -> navigate(navController, route) },
                onPlanClick = { planId -> navigate(navController, Route.MealPlanDetail(planId)) },
            )
        }

        // Create/edit meal plan
        composable<Route.CreateMealPlan> { backStackEntry ->
            val planId = backStackEntry.toRoute<Route.CreateMealPlan>().planId
            analyticsTracker?.logScreenView("create_meal_plan", "CreateMealPlanScreen")
            screens.CreateMealPlanScreen(
                planId = planId,
                onSave = { route ->
                    analyticsTracker?.logEvent("meal_plan_created", mapOf("plan_id" to (planId ?: "new")))
                    navigate(navController, route)
                },
                onCancel = { navController.popBackStack() },
            )
        }

        // Meal plan detail
        composable<Route.MealPlanDetail> { backStackEntry ->
            val planId = backStackEntry.toRoute<Route.MealPlanDetail>().planId
            analyticsTracker?.logScreenView("meal_plan_detail", "MealPlanDetailScreen")
            screens.MealPlanDetailScreen(
                planId = planId,
                onNavigate = { route -> navigate(navController, route) },
                onBack = { navController.popBackStack() },
            )
        }

        // Recipe search
        composable<Route.RecipeSearch> {
            analyticsTracker?.logScreenView("recipe_search", "RecipeSearchScreen")
            screens.RecipeSearchScreen(
                onNavigate = { route -> navigate(navController, route) },
                onRecipeClick = { recipeId -> navigate(navController, Route.RecipeDetail(recipeId)) },
            )
        }

        // Choose a recipe to add to a plan
        composable<Route.PickRecipe> { backStackEntry ->
            val planId = backStackEntry.toRoute<Route.PickRecipe>().planId
            analyticsTracker?.logScreenView("pick_recipe", "PickRecipeScreen")
            screens.PickRecipeScreen(
                planId = planId,
                onBack = { navController.popBackStack() },
            )
        }

        // Edit, rate or remove a planned meal
        composable<Route.EditMeal> { backStackEntry ->
            val route = backStackEntry.toRoute<Route.EditMeal>()
            analyticsTracker?.logScreenView("edit_meal", "EditMealScreen")
            screens.EditMealScreen(
                planId = route.planId,
                mealId = route.mealId,
                onBack = { navController.popBackStack() },
            )
        }

        // Add a recipe to a plan as a meal
        composable<Route.AddMeal> { backStackEntry ->
            val route = backStackEntry.toRoute<Route.AddMeal>()
            analyticsTracker?.logScreenView("add_meal", "AddMealScreen")
            screens.AddMealScreen(
                planId = route.planId,
                recipeId = route.recipeId,
                mealType = route.mealType,
                onBack = { navController.popBackStack() },
            )
        }

        // Choose the plan to add an AI recommendation to (AIA-604)
        composable<Route.PickPlan> { backStackEntry ->
            val route = backStackEntry.toRoute<Route.PickPlan>()
            analyticsTracker?.logScreenView("pick_plan", "PickPlanScreen")
            screens.PickPlanScreen(
                recipeId = route.recipeId,
                mealType = route.mealType,
                onBack = { navController.popBackStack() },
            )
        }

        // Favorite recipes
        composable<Route.FavoriteRecipes> {
            analyticsTracker?.logScreenView("favorite_recipes", "FavoriteRecipesScreen")
            screens.FavoriteRecipesScreen(
                onBack = { navController.popBackStack() },
            )
        }

        // Recipe detail
        composable<Route.RecipeDetail> { backStackEntry ->
            val recipeId = backStackEntry.toRoute<Route.RecipeDetail>().recipeId
            analyticsTracker?.logScreenView("recipe_detail", "RecipeDetailScreen")
            screens.RecipeDetailScreen(
                recipeId = recipeId,
                onBack = { navController.popBackStack() },
            )
        }

        // AI meal analysis
        composable<Route.AiMealAnalysis> {
            analyticsTracker?.logScreenView("ai_meal_analysis", "AiMealAnalysisScreen")
            screens.AiMealAnalysisScreen(
                onNavigate = { route -> navigate(navController, route) },
                onResult = { /* handle analysis result */ },
            )
        }

        // AI recommendations
        composable<Route.AiRecommendations> { backStackEntry ->
            analyticsTracker?.logScreenView("ai_recommendations", "AiRecommendationsScreen")
            screens.AiRecommendationsScreen(
                onNavigate = { route -> navigate(navController, route) },
                savedState = backStackEntry.savedStateHandle,
            )
        }

        // Order list
        composable<Route.OrderList> {
            analyticsTracker?.logScreenView("order_list", "OrderListScreen")
            screens.OrderListScreen(
                onNavigate = { route -> navigate(navController, route) },
                onOrderClick = { orderId -> navigate(navController, Route.OrderDetail(orderId)) },
            )
        }

        // Order detail
        composable<Route.OrderDetail> { backStackEntry ->
            val orderId = backStackEntry.toRoute<Route.OrderDetail>().orderId
            analyticsTracker?.logScreenView("order_detail", "OrderDetailScreen")
            screens.OrderDetailScreen(
                orderId = orderId,
                onBack = { navController.popBackStack() },
            )
        }

        // Checkout
        composable<Route.Checkout> {
            analyticsTracker?.logScreenView("checkout", "CheckoutScreen")
            screens.CheckoutScreen(
                onNavigate = { route -> navigate(navController, route) },
                onComplete = { route ->
                    analyticsTracker?.logEvent("checkout_complete", emptyMap())
                    analyticsTracker?.setUserProperty("activated", "true")
                    navigate(navController, route)
                },
                onCancel = { navController.popBackStack() },
            )
        }

        // Notification center
        composable<Route.NotificationCenter> {
            analyticsTracker?.logScreenView("notification_center", "NotificationCenterScreen")
            screens.NotificationCenterScreen(
                onNavigate = { route -> navigate(navController, route) },
                onNotificationClick = { /* handle notification click */ },
            )
        }

        // Profile
        composable<Route.Profile> {
            analyticsTracker?.logScreenView("profile", "ProfileScreen")
            screens.ProfileScreen(
                onNavigate = { route -> navigate(navController, route) },
            )
        }

        // Edit profile
        composable<Route.EditProfile> {
            analyticsTracker?.logScreenView("edit_profile", "EditProfileScreen")
            screens.EditProfileScreen(
                onSave = { route -> navigate(navController, route) },
                onBack = { navController.popBackStack() },
            )
        }

        // Dietary preferences
        composable<Route.DietaryPreferences> {
            analyticsTracker?.logScreenView("dietary_preferences", "DietaryPreferencesScreen")
            screens.DietaryPreferencesScreen(
                onSave = { route -> navigate(navController, route) },
                onBack = { navController.popBackStack() },
            )
        }

        // Deep link handler
        composable<Route.DeepLinkMeal> { backStackEntry ->
            val mealId = backStackEntry.toRoute<Route.DeepLinkMeal>().mealId
            analyticsTracker?.logScreenView("deep_link_meal", "DeepLinkMealScreen")
            screens.DeepLinkMealScreen(
                mealId = mealId,
                onBack = { navController.popBackStack() },
            )
        }

        composable<Route.DeepLinkPlan> { backStackEntry ->
            val planId = backStackEntry.toRoute<Route.DeepLinkPlan>().planId
            analyticsTracker?.logScreenView("deep_link_plan", "DeepLinkPlanScreen")
            screens.DeepLinkPlanScreen(
                planId = planId,
                onBack = { navController.popBackStack() },
            )
        }

        composable<Route.DeepLinkOrder> { backStackEntry ->
            val orderId = backStackEntry.toRoute<Route.DeepLinkOrder>().orderId
            analyticsTracker?.logScreenView("deep_link_order", "DeepLinkOrderScreen")
            screens.DeepLinkOrderScreen(
                orderId = orderId,
                onBack = { navController.popBackStack() },
            )
        }
    }
}

/** Navigate to a typed route. */
private fun navigate(
    navController: NavHostController,
    route: Any,
) {
    navController.navigate(route) {
        popUpTo(navController.graph.startDestinationId) { saveState = true }
        launchSingleTop = true
        restoreState = true
    }
}

/**
 * Interface for screen composable functions.
 *
 * Allows the navigation graph to be parameterized with actual screen implementations.
 */
interface AppNavigationScreens {
    @Composable fun SplashScreen(onNavigate: (Any) -> Unit)
    @Composable fun OnboardingScreen(onComplete: (Any) -> Unit)
    @Composable fun OnboardingWizardScreen(onComplete: (Any) -> Unit)
    @Composable fun AuthScreen(onLoginSuccess: (Any) -> Unit)
    @Composable fun MainScreen(onNavigate: (Any) -> Unit)
    @Composable fun MealPlanListScreen(
        onNavigate: (Any) -> Unit,
        onPlanClick: (String) -> Unit,
    )
    @Composable fun CreateMealPlanScreen(
        planId: String?,
        onSave: (Any) -> Unit,
        onCancel: () -> Unit,
    )
    @Composable fun MealPlanDetailScreen(
        planId: String,
        onNavigate: (Any) -> Unit,
        onBack: () -> Unit,
    )
    @Composable fun RecipeSearchScreen(
        onNavigate: (Any) -> Unit,
        onRecipeClick: (String) -> Unit,
    )
    @Composable fun FavoriteRecipesScreen(
        onBack: () -> Unit,
    )
    @Composable fun PickRecipeScreen(
        planId: String,
        onBack: () -> Unit,
    )
    @Composable fun EditMealScreen(
        planId: String,
        mealId: String,
        onBack: () -> Unit,
    )
    @Composable fun AddMealScreen(
        planId: String,
        recipeId: String,
        mealType: String?,
        onBack: () -> Unit,
    )
    @Composable fun PickPlanScreen(
        recipeId: String,
        mealType: String?,
        onBack: () -> Unit,
    )
    @Composable fun RecipeDetailScreen(
        recipeId: String,
        onBack: () -> Unit,
    )
    @Composable fun AiMealAnalysisScreen(
        onNavigate: (Any) -> Unit,
        onResult: (Resource<*>) -> Unit,
    )
    @Composable fun AiRecommendationsScreen(onNavigate: (Any) -> Unit, savedState: SavedStateHandle)
    @Composable fun OrderListScreen(
        onNavigate: (Any) -> Unit,
        onOrderClick: (String) -> Unit,
    )
    @Composable fun OrderDetailScreen(
        orderId: String,
        onBack: () -> Unit,
    )
    @Composable fun CheckoutScreen(
        onNavigate: (Any) -> Unit,
        onComplete: (Any) -> Unit,
        onCancel: () -> Unit,
    )
    @Composable fun NotificationCenterScreen(
        onNavigate: (Any) -> Unit,
        onNotificationClick: (String) -> Unit,
    )
    @Composable fun ProfileScreen(onNavigate: (Any) -> Unit)
    @Composable fun EditProfileScreen(
        onSave: (Any) -> Unit,
        onBack: () -> Unit,
    )
    @Composable fun DietaryPreferencesScreen(
        onSave: (Any) -> Unit,
        onBack: () -> Unit,
    )
    @Composable fun DeepLinkMealScreen(
        mealId: String,
        onBack: () -> Unit,
    )
    @Composable fun DeepLinkPlanScreen(
        planId: String,
        onBack: () -> Unit,
    )
    @Composable fun DeepLinkOrderScreen(
        orderId: String,
        onBack: () -> Unit,
    )
}
