package com.nutriplan.android

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.navigation.NavDestination.Companion.hasRoute
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.nutriplan.android.screen.auth.LoginScreen
import com.nutriplan.android.screen.checkout.CheckoutScreen
import com.nutriplan.android.screen.home.HomeScreen
import com.nutriplan.android.screen.onboarding.OnboardingScreen
import com.nutriplan.android.screen.profile.ProfileScreen
import com.nutriplan.android.navigation.AppNavigationGraph
import com.nutriplan.android.di.koinInject
import com.nutriplan.shared.data.repository.AuthRepository
import com.nutriplan.shared.navigation.PendingDeepLink
import com.nutriplan.shared.navigation.Route
import com.nutriplan.android.ui.theme.NutriPlanTheme

/**
 * Main activity entry point for the NutriPlan Android app.
 *
 * Sets up the Compose navigation graph and applies the NutriPlan theme.
 */
class MainActivity : ComponentActivity() {

    /** Link from outside the app (notification tap, browser) waiting for an authenticated user. */
    private val pendingDeepLink = PendingDeepLink()

    /** Bumped whenever a new link is accepted so the UI re-checks whether it can be opened. */
    private var deepLinkVersion by mutableIntStateOf(0)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        offerDeepLink(intent)
        setContent {
            NutriPlanTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    val navController = rememberNavController()
                    val authRepository = koinInject<AuthRepository>()

                    fun openPendingDeepLink(isAuthenticated: Boolean) {
                        pendingDeepLink.takeIfAuthenticated(isAuthenticated)?.let { navController.navigate(it) }
                    }

                    // Open a waiting link as soon as the user is signed in, but never while the splash
                    // screen is still deciding where to go (it would pop the link off the back stack).
                    val currentEntry by navController.currentBackStackEntryAsState()
                    val onSplash = currentEntry?.destination?.hasRoute<Route.Splash>() != false
                    LaunchedEffect(deepLinkVersion, onSplash) {
                        if (!onSplash) openPendingDeepLink(authRepository.isAuthenticated)
                    }

                    AppNavigationGraph(
                        navController = navController,
                        startDestination = Route.Splash,
                        screens = remember(navController) {
                            // Not signed in: the link waits and opens right after a successful login.
                            MainNavigationScreens(navController, onAuthenticated = { openPendingDeepLink(true) })
                        },
                    )
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        offerDeepLink(intent)
    }

    /**
     * A VIEW intent carries the link in its data; a tapped push notification delivered by the
     * system tray carries the payload as extras, with the target under `deepLink`.
     */
    private fun offerDeepLink(intent: Intent?) {
        val link = intent?.data?.toString() ?: intent?.getStringExtra(NOTIFICATION_DEEP_LINK_EXTRA)
        if (pendingDeepLink.offer(link)) deepLinkVersion++
    }

    private companion object {
        const val NOTIFICATION_DEEP_LINK_EXTRA = "deepLink"
    }
}

/**
 * Concrete implementation of [AppNavigationScreens] for the Android app.
 *
 * Each screen composable is implemented with actual UI components.
 */
class MainNavigationScreens(
    private val navController: androidx.navigation.NavHostController,
    private val onAuthenticated: () -> Unit = {},
) : com.nutriplan.android.navigation.AppNavigationScreens {

    @Composable
    override fun SplashScreen(onNavigate: (Any) -> Unit) {
        val authRepository = koinInject<AuthRepository>()
        // The session was restored from secure storage when the repository was created.
        LaunchedEffect(Unit) {
            onNavigate(if (authRepository.isAuthenticated) Route.Main else Route.Auth)
        }
        SplashScreenContent()
    }

    @Composable
    override fun OnboardingScreen(onComplete: (Any) -> Unit) {
        com.nutriplan.android.screen.onboarding.OnboardingScreen(onGetStarted = { onComplete(Route.Auth) })
    }

    @Composable
    override fun AuthScreen(onLoginSuccess: (Any) -> Unit) {
        LoginScreen(
            onLoginSuccess = {
                onLoginSuccess(Route.Main)
                onAuthenticated()
            },
            onNavigateToRegister = { /* TODO: Navigate to register */ },
            onNavigateToForgotPassword = { /* TODO: Navigate to forgot password */ }
        )
    }

    @Composable
    override fun MainScreen(onNavigate: (Any) -> Unit) {
        HomeScreen(
            onNavigateToMealPlanDetail = { planId -> onNavigate(Route.MealPlanDetail(planId)) },
            onNavigateToCreateMealPlan = { onNavigate(Route.CreateMealPlan(null)) },
            onNavigateToRecipeSearch = { onNavigate(Route.RecipeSearch) },
            onNavigateToAiRecommendations = { onNavigate(Route.AiRecommendations) }
        )
    }

    @Composable
    override fun MealPlanListScreen(
        onNavigate: (Any) -> Unit,
        onPlanClick: (String) -> Unit,
    ) {
        MealPlanListScreenContent(onNavigate, onPlanClick)
    }

    @Composable
    override fun CreateMealPlanScreen(
        planId: String?,
        onSave: (Any) -> Unit,
        onCancel: () -> Unit,
    ) {
        CreateMealPlanScreenContent(planId, onSave, onCancel)
    }

    @Composable
    override fun MealPlanDetailScreen(
        planId: String,
        onNavigate: (Any) -> Unit,
        onBack: () -> Unit,
    ) {
        MealPlanDetailScreenContent(planId, onNavigate, onBack)
    }

    @Composable
    override fun RecipeSearchScreen(
        onNavigate: (Any) -> Unit,
        onRecipeClick: (String) -> Unit,
    ) {
        RecipeSearchScreenContent(onNavigate, onRecipeClick)
    }

    @Composable
    override fun RecipeDetailScreen(
        recipeId: String,
        onBack: () -> Unit,
    ) {
        RecipeDetailScreenContent(recipeId, onBack)
    }

    @Composable
    override fun AiMealAnalysisScreen(
        onNavigate: (Any) -> Unit,
        onResult: (com.nutriplan.shared.domain.Resource<*>) -> Unit,
    ) {
        AiMealAnalysisScreenContent(onNavigate, onResult)
    }

    @Composable
    override fun AiRecommendationsScreen(onNavigate: (Any) -> Unit) {
        AiRecommendationsScreenContent(onNavigate)
    }

    @Composable
    override fun OrderListScreen(
        onNavigate: (Any) -> Unit,
        onOrderClick: (String) -> Unit,
    ) {
        OrderListScreenContent(onNavigate, onOrderClick)
    }

    @Composable
    override fun OrderDetailScreen(
        orderId: String,
        onBack: () -> Unit,
    ) {
        OrderDetailScreenContent(orderId, onBack)
    }

    @Composable
    override fun CheckoutScreen(
        onNavigate: (Any) -> Unit,
        onComplete: (Any) -> Unit,
        onCancel: () -> Unit,
    ) {
        CheckoutScreen(
            planId = "default-plan-id",
            onCheckoutSuccess = { onComplete(Route.OrderList) },
            onNavigateBack = onCancel
        )
    }

    @Composable
    override fun NotificationCenterScreen(
        onNavigate: (Any) -> Unit,
        onNotificationClick: (String) -> Unit,
    ) {
        NotificationCenterScreenContent(onNavigate, onNotificationClick)
    }

    @Composable
    override fun ProfileScreen(onNavigate: (Any) -> Unit) {
        val authRepository = koinInject<AuthRepository>()
        ProfileScreen(
            onNavigateToEditProfile = { onNavigate(Route.EditProfile) },
            onNavigateToDietaryPreferences = { onNavigate(Route.DietaryPreferences) },
            onNavigateToOrderHistory = { onNavigate(Route.OrderList) },
            onNavigateToNotificationSettings = { onNavigate(Route.NotificationCenter) },
            onLogout = {
                // End the session (also wipes it from secure storage) and drop the whole back
                // stack so Back cannot return to a signed-in screen.
                authRepository.clearTokens()
                navController.navigate(Route.Auth) {
                    popUpTo(navController.graph.id) { inclusive = true }
                }
            }
        )
    }

    @Composable
    override fun EditProfileScreen(
        onSave: (Any) -> Unit,
        onBack: () -> Unit,
    ) {
        EditProfileScreenContent(onSave, onBack)
    }

    @Composable
    override fun DietaryPreferencesScreen(
        onSave: (Any) -> Unit,
        onBack: () -> Unit,
    ) {
        DietaryPreferencesScreenContent(onSave, onBack)
    }

    @Composable
    override fun DeepLinkMealScreen(
        mealId: String,
        onBack: () -> Unit,
    ) {
        DeepLinkMealScreenContent(mealId, onBack)
    }

    @Composable
    override fun DeepLinkPlanScreen(
        planId: String,
        onBack: () -> Unit,
    ) {
        DeepLinkPlanScreenContent(planId, onBack)
    }

    @Composable
    override fun DeepLinkOrderScreen(
        orderId: String,
        onBack: () -> Unit,
    ) {
        DeepLinkOrderScreenContent(orderId, onBack)
    }
}

// --- Placeholder screen composables ---

@Composable
private fun SplashScreenContent() {
    androidx.compose.foundation.layout.Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        androidx.compose.material3.CircularProgressIndicator()
    }
}

@Composable
private fun OnboardingScreenContent(onComplete: (Any) -> Unit) {
    androidx.compose.foundation.layout.Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        androidx.compose.material3.Text("Onboarding", style = MaterialTheme.typography.headlineLarge)
    }
}

@Composable
private fun AuthScreenContent(onLoginSuccess: (Any) -> Unit) {
    androidx.compose.foundation.layout.Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        androidx.compose.material3.Text("Auth", style = MaterialTheme.typography.headlineLarge)
    }
}

@Composable
private fun MainScreenContent(onNavigate: (Any) -> Unit) {
    androidx.compose.foundation.layout.Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        androidx.compose.material3.Text("Main", style = MaterialTheme.typography.headlineLarge)
    }
}

@Composable
private fun MealPlanListScreenContent(
    onNavigate: (Any) -> Unit,
    onPlanClick: (String) -> Unit,
) {
    androidx.compose.foundation.layout.Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        androidx.compose.material3.Text("Meal Plans", style = MaterialTheme.typography.headlineLarge)
    }
}

@Composable
private fun CreateMealPlanScreenContent(
    planId: String?,
    onSave: (Any) -> Unit,
    onCancel: () -> Unit,
) {
    androidx.compose.foundation.layout.Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        androidx.compose.material3.Text("Create Plan", style = MaterialTheme.typography.headlineLarge)
    }
}

@Composable
private fun MealPlanDetailScreenContent(
    planId: String,
    onNavigate: (Any) -> Unit,
    onBack: () -> Unit,
) {
    androidx.compose.foundation.layout.Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        androidx.compose.material3.Text("Plan Detail: $planId", style = MaterialTheme.typography.headlineLarge)
    }
}

@Composable
private fun RecipeSearchScreenContent(
    onNavigate: (Any) -> Unit,
    onRecipeClick: (String) -> Unit,
) {
    androidx.compose.foundation.layout.Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        androidx.compose.material3.Text("Recipes", style = MaterialTheme.typography.headlineLarge)
    }
}

@Composable
private fun RecipeDetailScreenContent(recipeId: String, onBack: () -> Unit) {
    androidx.compose.foundation.layout.Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        androidx.compose.material3.Text("Recipe: $recipeId", style = MaterialTheme.typography.headlineLarge)
    }
}

@Composable
private fun AiMealAnalysisScreenContent(
    onNavigate: (Any) -> Unit,
    onResult: (com.nutriplan.shared.domain.Resource<*>) -> Unit,
) {
    androidx.compose.foundation.layout.Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        androidx.compose.material3.Text("AI Analysis", style = MaterialTheme.typography.headlineLarge)
    }
}

@Composable
private fun AiRecommendationsScreenContent(onNavigate: (Any) -> Unit) {
    androidx.compose.foundation.layout.Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        androidx.compose.material3.Text("AI Recommendations", style = MaterialTheme.typography.headlineLarge)
    }
}

@Composable
private fun OrderListScreenContent(
    onNavigate: (Any) -> Unit,
    onOrderClick: (String) -> Unit,
) {
    androidx.compose.foundation.layout.Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        androidx.compose.material3.Text("Orders", style = MaterialTheme.typography.headlineLarge)
    }
}

@Composable
private fun OrderDetailScreenContent(orderId: String, onBack: () -> Unit) {
    androidx.compose.foundation.layout.Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        androidx.compose.material3.Text("Order: $orderId", style = MaterialTheme.typography.headlineLarge)
    }
}

@Composable
private fun CheckoutScreenContent(
    onNavigate: (Any) -> Unit,
    onComplete: (Any) -> Unit,
    onCancel: () -> Unit,
) {
    androidx.compose.foundation.layout.Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        androidx.compose.material3.Text("Checkout", style = MaterialTheme.typography.headlineLarge)
    }
}

@Composable
private fun NotificationCenterScreenContent(
    onNavigate: (Any) -> Unit,
    onNotificationClick: (String) -> Unit,
) {
    androidx.compose.foundation.layout.Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        androidx.compose.material3.Text("Notifications", style = MaterialTheme.typography.headlineLarge)
    }
}

@Composable
private fun ProfileScreenContent(onNavigate: (Any) -> Unit) {
    androidx.compose.foundation.layout.Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        androidx.compose.material3.Text("Profile", style = MaterialTheme.typography.headlineLarge)
    }
}

@Composable
private fun EditProfileScreenContent(
    onSave: (Any) -> Unit,
    onBack: () -> Unit,
) {
    androidx.compose.foundation.layout.Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        androidx.compose.material3.Text("Edit Profile", style = MaterialTheme.typography.headlineLarge)
    }
}

@Composable
private fun DietaryPreferencesScreenContent(
    onSave: (Any) -> Unit,
    onBack: () -> Unit,
) {
    androidx.compose.foundation.layout.Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        androidx.compose.material3.Text("Dietary Preferences", style = MaterialTheme.typography.headlineLarge)
    }
}

@Composable
private fun DeepLinkMealScreenContent(mealId: String, onBack: () -> Unit) {
    androidx.compose.foundation.layout.Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        androidx.compose.material3.Text("Meal: $mealId", style = MaterialTheme.typography.headlineLarge)
    }
}

@Composable
private fun DeepLinkPlanScreenContent(planId: String, onBack: () -> Unit) {
    androidx.compose.foundation.layout.Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        androidx.compose.material3.Text("Plan: $planId", style = MaterialTheme.typography.headlineLarge)
    }
}

@Composable
private fun DeepLinkOrderScreenContent(orderId: String, onBack: () -> Unit) {
    androidx.compose.foundation.layout.Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        androidx.compose.material3.Text("Order: $orderId", style = MaterialTheme.typography.headlineLarge)
    }
}
