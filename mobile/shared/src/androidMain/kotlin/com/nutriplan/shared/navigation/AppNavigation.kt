package com.nutriplan.shared.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.toRoute
import com.nutriplan.shared.domain.Resource

/**
 * Top-level navigation graph for the NutriPlan app.
 *
 * Routes are typed via [Route] objects for compile-time safety.
 * Screen composable functions are passed in as parameters to keep
 * this file focused on navigation wiring.
 */
@Composable
fun AppNavigationGraph(
    navController: NavHostController,
    startDestination: Any = Route.Splash,
    onAuthStateChanged: (Boolean) -> Unit = {},
    onDeepLink: (String) -> Unit = {},
    screens: AppNavigationScreens,
) {
    NavHost(
        navController = navController,
        startDestination = startDestination,
    ) {
        // Splash screen
        composable<Route.Splash> {
            screens.SplashScreen(
                onNavigate = { route -> navigate(navController, route) },
            )
        }

        // Onboarding
        composable<Route.Onboarding> {
            screens.OnboardingScreen(
                onComplete = { route -> navigate(navController, route) },
            )
        }

        // Auth
        composable<Route.Auth> {
            screens.AuthScreen(
                onLoginSuccess = { route -> navigate(navController, route) },
            )
        }

        // Main app
        composable<Route.Main> {
            screens.MainScreen(
                onNavigate = { route -> navigate(navController, route) },
            )
        }

        // Meal plan list
        composable<Route.MealPlanList> {
            screens.MealPlanListScreen(
                onNavigate = { route -> navigate(navController, route) },
                onPlanClick = { planId -> navigate(navController, Route.MealPlanDetail(planId)) },
            )
        }

        // Create/edit meal plan
        composable<Route.CreateMealPlan> { backStackEntry ->
            val planId = backStackEntry.toRoute<Route.CreateMealPlan>().planId
            screens.CreateMealPlanScreen(
                planId = planId,
                onSave = { route -> navigate(navController, route) },
                onCancel = { navController.popBackStack() },
            )
        }

        // Meal plan detail
        composable<Route.MealPlanDetail> { backStackEntry ->
            val planId = backStackEntry.toRoute<Route.MealPlanDetail>().planId
            screens.MealPlanDetailScreen(
                planId = planId,
                onNavigate = { route -> navigate(navController, route) },
                onBack = { navController.popBackStack() },
            )
        }

        // Recipe search
        composable<Route.RecipeSearch> {
            screens.RecipeSearchScreen(
                onNavigate = { route -> navigate(navController, route) },
                onRecipeClick = { recipeId -> navigate(navController, Route.RecipeDetail(recipeId)) },
            )
        }

        // Recipe detail
        composable<Route.RecipeDetail> { backStackEntry ->
            val recipeId = backStackEntry.toRoute<Route.RecipeDetail>().recipeId
            screens.RecipeDetailScreen(
                recipeId = recipeId,
                onBack = { navController.popBackStack() },
            )
        }

        // AI meal analysis
        composable<Route.AiMealAnalysis> {
            screens.AiMealAnalysisScreen(
                onNavigate = { route -> navigate(navController, route) },
                onResult = { /* handle analysis result */ },
            )
        }

        // AI recommendations
        composable<Route.AiRecommendations> {
            screens.AiRecommendationsScreen(
                onNavigate = { route -> navigate(navController, route) },
            )
        }

        // Order list
        composable<Route.OrderList> {
            screens.OrderListScreen(
                onNavigate = { route -> navigate(navController, route) },
                onOrderClick = { orderId -> navigate(navController, Route.OrderDetail(orderId)) },
            )
        }

        // Order detail
        composable<Route.OrderDetail> { backStackEntry ->
            val orderId = backStackEntry.toRoute<Route.OrderDetail>().orderId
            screens.OrderDetailScreen(
                orderId = orderId,
                onBack = { navController.popBackStack() },
            )
        }

        // Checkout
        composable<Route.Checkout> {
            screens.CheckoutScreen(
                onNavigate = { route -> navigate(navController, route) },
                onComplete = { route -> navigate(navController, route) },
                onCancel = { navController.popBackStack() },
            )
        }

        // Notification center
        composable<Route.NotificationCenter> {
            screens.NotificationCenterScreen(
                onNavigate = { route -> navigate(navController, route) },
                onNotificationClick = { /* handle notification click */ },
            )
        }

        // Profile
        composable<Route.Profile> {
            screens.ProfileScreen(
                onNavigate = { route -> navigate(navController, route) },
            )
        }

        // Edit profile
        composable<Route.EditProfile> {
            screens.EditProfileScreen(
                onSave = { route -> navigate(navController, route) },
                onBack = { navController.popBackStack() },
            )
        }

        // Dietary preferences
        composable<Route.DietaryPreferences> {
            screens.DietaryPreferencesScreen(
                onSave = { route -> navigate(navController, route) },
                onBack = { navController.popBackStack() },
            )
        }

        // Deep link handler
        composable<Route.DeepLinkMeal> { backStackEntry ->
            val mealId = backStackEntry.toRoute<Route.DeepLinkMeal>().mealId
            screens.DeepLinkMealScreen(
                mealId = mealId,
                onBack = { navController.popBackStack() },
            )
        }

        composable<Route.DeepLinkPlan> { backStackEntry ->
            val planId = backStackEntry.toRoute<Route.DeepLinkPlan>().planId
            screens.DeepLinkPlanScreen(
                planId = planId,
                onBack = { navController.popBackStack() },
            )
        }

        composable<Route.DeepLinkOrder> { backStackEntry ->
            val orderId = backStackEntry.toRoute<Route.DeepLinkOrder>().orderId
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
    @Composable fun RecipeDetailScreen(
        recipeId: String,
        onBack: () -> Unit,
    )
    @Composable fun AiMealAnalysisScreen(
        onNavigate: (Any) -> Unit,
        onResult: (Resource<*>) -> Unit,
    )
    @Composable fun AiRecommendationsScreen(onNavigate: (Any) -> Unit)
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
