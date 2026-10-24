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
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.lifecycle.SavedStateHandle
import androidx.navigation.NavDestination.Companion.hasRoute
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.nutriplan.android.screen.auth.LoginScreen
import com.nutriplan.android.screen.auth.RegisterScreen
import com.nutriplan.android.screen.home.HomeScreen
import com.nutriplan.android.screen.onboarding.OnboardingScreen
import com.nutriplan.android.screen.onboarding.OnboardingWizardScreen
import com.nutriplan.android.screen.profile.ProfileScreen
import com.nutriplan.android.navigation.AppNavigationGraph
import com.nutriplan.android.navigation.SessionGate
import com.nutriplan.android.di.koinInject
import com.nutriplan.android.auth.CurrentActivity
import com.nutriplan.shared.data.repository.AuthRepository
import com.nutriplan.shared.notifications.NotificationsViewModel
import com.nutriplan.shared.navigation.PendingDeepLink
import com.nutriplan.shared.session.SignOut
import com.nutriplan.shared.session.SessionManager
import com.nutriplan.shared.session.SessionState
import com.nutriplan.shared.navigation.Route
import kotlinx.coroutines.flow.map
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
        // IDN-505: let the OAuth token provider launch the native consent UI.
        CurrentActivity.set(this)
        offerDeepLink(intent)
        setContent {
            NutriPlanTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    val navController = rememberNavController()
                    val authRepository = koinInject<AuthRepository>()
                    val analyticsTracker = (application as NutriPlanApplication).analyticsTracker

                    // DPL-509: leave signed-in screens as soon as the session ends.
                    val sessionManager = koinInject<SessionManager>()
                    val sessionState by sessionManager.state.collectAsState()
                    SessionGate(navController, sessionState)

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
                        analyticsTracker = analyticsTracker,
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
        val sessionManager = koinInject<SessionManager>()
        // Route per session state: fully onboarded users go to the main graph, authenticated but
        // not-yet-onboarded users into the wizard, and everyone else to auth.
        LaunchedEffect(Unit) {
            onNavigate(
                when (sessionManager.state.value) {
                    is SessionState.SignedIn -> Route.Main
                    SessionState.Onboarding -> Route.OnboardingWizard
                    SessionState.SignedOut -> Route.Auth
                },
            )
        }
        SplashScreenContent()
    }

    @Composable
    override fun OnboardingScreen(onComplete: (Any) -> Unit) {
        com.nutriplan.android.screen.onboarding.OnboardingScreen(onGetStarted = { onComplete(Route.Auth) })
    }

    @Composable
    override fun OnboardingWizardScreen(onComplete: (Any) -> Unit) {
        com.nutriplan.android.screen.onboarding.OnboardingWizardScreen(
            onComplete = {
                onComplete(Route.Main)
                onAuthenticated()
            },
        )
    }

    @Composable
    override fun AuthScreen(onLoginSuccess: (Any) -> Unit) {
        // A lightweight toggle keeps login and registration on one destination without a new route.
        var showRegister by remember { mutableStateOf(false) }
        val sessionManager = koinInject<SessionManager>()
        val onSuccess: () -> Unit = {
            // New users have no dietary preferences yet and must go through the wizard.
            val route: Any = when (sessionManager.state.value) {
                is SessionState.SignedIn -> Route.Main
                else -> Route.OnboardingWizard
            }
            onLoginSuccess(route)
            onAuthenticated()
        }
        if (showRegister) {
            RegisterScreen(
                onRegisterSuccess = onSuccess,
                onNavigateToLogin = { showRegister = false },
            )
        } else {
            LoginScreen(
                onLoginSuccess = onSuccess,
                onNavigateToRegister = { showRegister = true },
                onNavigateToForgotPassword = { /* TODO: Navigate to forgot password */ },
            )
        }
    }

    @Composable
    override fun MainScreen(onNavigate: (Any) -> Unit) {
        val notificationsViewModel = koinInject<NotificationsViewModel>()
        val unreadCount by notificationsViewModel.state.map { it.unreadCount }.collectAsState()

        HomeScreen(
            onNavigateToMealPlanDetail = { planId -> onNavigate(Route.MealPlanDetail(planId)) },
            onNavigateToCreateMealPlan = { onNavigate(Route.CreateMealPlan(null)) },
            onNavigateToRecipeSearch = { onNavigate(Route.RecipeSearch) },
            onNavigateToAiRecommendations = { onNavigate(Route.AiRecommendations) },
            onNavigateToAnalyzeMeal = { onNavigate(Route.AiMealAnalysis) },
            onNavigateToMealPlans = { onNavigate(Route.MealPlanList) },
            onNavigateToNotifications = { onNavigate(Route.NotificationCenter) },
            unreadCount = unreadCount,
        )
    }

    @Composable
    override fun MealPlanListScreen(
        onNavigate: (Any) -> Unit,
        onPlanClick: (String) -> Unit,
    ) {
        val sessionManager = koinInject<SessionManager>()
        com.nutriplan.android.screen.plans.MealPlanListScreen(
            onPlanClick = onPlanClick,
            onCreatePlan = { onNavigate(Route.CreateMealPlan(null)) },
            onBack = { navController.popBackStack() },
            // The server rejected the session: end it, and SessionGate returns the user to sign-in.
            onSessionExpired = { sessionManager.onSignedOut() },
        )
    }

    @Composable
    override fun CreateMealPlanScreen(
        planId: String?,
        onSave: (Any) -> Unit,
        onCancel: () -> Unit,
    ) {
        // Plans can only be created: the API has no endpoint to edit one (PATCH only changes its
        // status), so a plan id is not used.
        val sessionManager = koinInject<SessionManager>()
        com.nutriplan.android.screen.plans.MealPlanFormScreen(
            onBack = onCancel,
            // Open the new plan and drop the form from the back stack, so Back does not return to it.
            onCreated = { createdId ->
                navController.navigate(Route.MealPlanDetail(createdId)) {
                    popUpTo<Route.CreateMealPlan> { inclusive = true }
                }
            },
            onSessionExpired = { sessionManager.onSignedOut() },
        )
    }

    @Composable
    override fun MealPlanDetailScreen(
        planId: String,
        onNavigate: (Any) -> Unit,
        onBack: () -> Unit,
    ) {
        val sessionManager = koinInject<SessionManager>()
        com.nutriplan.android.screen.plans.MealPlanDetailScreen(
            planId = planId,
            onBack = onBack,
            onAddMeal = { navController.navigate(Route.PickRecipe(planId)) },
            onEditMeal = { mealId -> navController.navigate(Route.EditMeal(planId, mealId)) },
            onSessionExpired = { sessionManager.onSignedOut() },
            onOptimize = { navController.navigate(Route.OptimizePlan(planId)) },
            // COM-605: order the plan (checkout opens with it chosen).
            onOrder = { navController.navigate(Route.Checkout(planId)) },
        )
    }

    @Composable
    override fun OptimizePlanScreen(
        planId: String,
        onBack: () -> Unit,
    ) {
        val sessionManager = koinInject<SessionManager>()
        com.nutriplan.android.screen.ai.OptimizePlanScreen(
            planId = planId,
            onBack = onBack,
            // Back to the plan, which reloads to show the new servings.
            onDone = { navController.popBackStack() },
            onSessionExpired = { sessionManager.onSignedOut() },
        )
    }

    @Composable
    override fun RecipeSearchScreen(
        onNavigate: (Any) -> Unit,
        onRecipeClick: (String) -> Unit,
    ) {
        val sessionManager = koinInject<SessionManager>()
        com.nutriplan.android.screen.recipes.RecipeSearchScreen(
            onBack = { navController.popBackStack() },
            // Pushed on top of the search so Back returns to it.
            onRecipeClick = { recipeId -> navController.navigate(Route.RecipeDetail(recipeId)) },
            onSessionExpired = { sessionManager.onSignedOut() },
            onOpenFavorites = { navController.navigate(Route.FavoriteRecipes) },
        )
    }

    @Composable
    override fun FavoriteRecipesScreen(onBack: () -> Unit) {
        val sessionManager = koinInject<SessionManager>()
        com.nutriplan.android.screen.recipes.FavoriteRecipesScreen(
            onBack = onBack,
            onRecipeClick = { recipeId -> navController.navigate(Route.RecipeDetail(recipeId)) },
            onSessionExpired = { sessionManager.onSignedOut() },
        )
    }

    @Composable
    override fun PickRecipeScreen(
        planId: String,
        onBack: () -> Unit,
    ) {
        val sessionManager = koinInject<SessionManager>()
        com.nutriplan.android.screen.recipes.RecipeSearchScreen(
            onBack = onBack,
            // Skip the recipe page: the user already said they want to add it.
            onRecipeClick = { recipeId -> navController.navigate(Route.AddMeal(planId, recipeId)) },
            onSessionExpired = { sessionManager.onSignedOut() },
            isPicking = true,
        )
    }

    @Composable
    override fun EditMealScreen(
        planId: String,
        mealId: String,
        onBack: () -> Unit,
    ) {
        val sessionManager = koinInject<SessionManager>()
        com.nutriplan.android.screen.plans.EditMealScreen(
            planId = planId,
            mealId = mealId,
            onBack = onBack,
            // Back to the plan, which reloads to show the change.
            onDone = { navController.popBackStack() },
            onSessionExpired = { sessionManager.onSignedOut() },
        )
    }

    @Composable
    override fun AddMealScreen(
        planId: String,
        recipeId: String,
        mealType: String?,
        onBack: () -> Unit,
    ) {
        val sessionManager = koinInject<SessionManager>()
        com.nutriplan.android.screen.plans.AddMealScreen(
            planId = planId,
            recipeId = recipeId,
            mealType = mealType,
            onBack = onBack,
            onDone = {
                val previous = navController.previousBackStackEntry?.destination
                val fromRecommendations = previous?.hasRoute<Route.PickPlan>() == true
                if (fromRecommendations) {
                    // AIA-604: back to the recommendations, which confirm the add, to pick another.
                    navController.getBackStackEntry<Route.AiRecommendations>().savedStateHandle[AI_MEAL_ADDED] = true
                    navController.popBackStack<Route.AiRecommendations>(inclusive = false)
                } else {
                    // Back to the plan: drop the picker and the form, so Back does not return to them.
                    navController.popBackStack<Route.MealPlanDetail>(inclusive = false)
                }
            },
            onSessionExpired = { sessionManager.onSignedOut() },
        )
    }

    @Composable
    override fun PickPlanScreen(
        recipeId: String,
        mealType: String?,
        onBack: () -> Unit,
    ) {
        val sessionManager = koinInject<SessionManager>()
        com.nutriplan.android.screen.plans.MealPlanListScreen(
            onPlanClick = { planId -> navController.navigate(Route.AddMeal(planId, recipeId, mealType)) },
            onCreatePlan = {},
            onBack = onBack,
            onSessionExpired = { sessionManager.onSignedOut() },
            isPicking = true,
        )
    }

    @Composable
    override fun RecipeDetailScreen(
        recipeId: String,
        onBack: () -> Unit,
    ) {
        val sessionManager = koinInject<SessionManager>()
        com.nutriplan.android.screen.recipes.RecipeDetailScreen(
            recipeId = recipeId,
            onBack = onBack,
            onSessionExpired = { sessionManager.onSignedOut() },
        )
    }

    @Composable
    override fun AiMealAnalysisScreen(onBack: () -> Unit) {
        val sessionManager = koinInject<SessionManager>()
        com.nutriplan.android.screen.ai.AnalyzeMealScreen(
            onBack = onBack,
            onSessionExpired = { sessionManager.onSignedOut() },
        )
    }

    @Composable
    override fun AiRecommendationsScreen(onNavigate: (Any) -> Unit, savedState: SavedStateHandle) {
        val sessionManager = koinInject<SessionManager>()
        // Set by the add-meal form when a recommendation was added to a plan (AIA-604).
        val mealAdded by savedState.getStateFlow(AI_MEAL_ADDED, false).collectAsState()
        com.nutriplan.android.screen.ai.AiRecommendationsScreen(
            onBack = { navController.popBackStack() },
            // Pushed on top of the recommendations so Back returns to them.
            onRecipeClick = { recipeId -> navController.navigate(Route.RecipeDetail(recipeId)) },
            onSessionExpired = { sessionManager.onSignedOut() },
            onAddToPlan = { recipeId, mealType -> navController.navigate(Route.PickPlan(recipeId, mealType)) },
            mealAdded = mealAdded,
            onMealAddedShown = { savedState[AI_MEAL_ADDED] = false },
            // AIA-606: when the AI cannot answer, the regular recipe search is the way out.
            onBrowseRecipes = { navController.navigate(Route.RecipeSearch) },
        )
    }

    @Composable
    override fun OrderListScreen(
        onNavigate: (Any) -> Unit,
        onOrderClick: (String) -> Unit,
    ) {
        val sessionManager = koinInject<SessionManager>()
        com.nutriplan.android.screen.orders.OrderListScreen(
            onOrderClick = onOrderClick,
            onReorder = { orderId -> onNavigate(Route.Checkout(reorderOrderId = orderId)) },
            onBrowsePlans = { onNavigate(Route.MealPlanList) },
            onBack = { navController.popBackStack() },
            onSessionExpired = { sessionManager.onSignedOut() },
        )
    }

    @Composable
    override fun OrderDetailScreen(
        orderId: String,
        onBack: () -> Unit,
    ) {
        val sessionManager = koinInject<SessionManager>()
        com.nutriplan.android.screen.orders.OrderDetailScreen(
            orderId = orderId,
            onBack = onBack,
            onSessionExpired = { sessionManager.onSignedOut() },
        )
    }

    @Composable
    override fun CheckoutScreen(
        planId: String?,
        reorderOrderId: String?,
        onNavigate: (Any) -> Unit,
        onComplete: (Any) -> Unit,
        onCancel: () -> Unit,
    ) {
        val sessionManager = koinInject<SessionManager>()
        com.nutriplan.android.screen.checkout.CheckoutScreen(
            planId = planId,
            reorderOrderId = reorderOrderId,
            onOrderPlaced = { orderId -> onComplete(Route.OrderDetail(orderId)) },
            onManageAddresses = { onNavigate(Route.AddressBook) },
            onBack = onCancel,
            onSessionExpired = { sessionManager.onSignedOut() },
        )
    }

    @Composable
    override fun NotificationCenterScreen(
        onNavigate: (Any) -> Unit,
        onNotificationClick: (String) -> Unit,
    ) {
        com.nutriplan.android.screen.notifications.NotificationsScreen(
            onNotificationClick = onNotificationClick,
        )
    }

    @Composable
    override fun ProfileScreen(onNavigate: (Any) -> Unit) {
        val signOut = koinInject<SignOut>()
        ProfileScreen(
            onNavigateToEditProfile = { onNavigate(Route.EditProfile) },
            onNavigateToDietaryPreferences = { onNavigate(Route.DietaryPreferences) },
            onNavigateToAddresses = { onNavigate(Route.AddressBook) },
            onNavigateToPaymentMethods = { onNavigate(Route.PaymentMethods) },
            onNavigateToOrderHistory = { onNavigate(Route.OrderList) },
            onNavigateToNotificationSettings = { onNavigate(Route.NotificationCenter) },
            onLogout = {
                // End the session (secure storage and cached personal data included) and drop the
                // whole back stack so Back cannot return to a signed-in screen.
                signOut()
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
        com.nutriplan.android.screen.profile.EditProfileScreen(
            onDone = { navController.popBackStack() },
            onBack = onBack,
        )
    }

    @Composable
    override fun DietaryPreferencesScreen(
        onSave: (Any) -> Unit,
        onBack: () -> Unit,
    ) {
        com.nutriplan.android.screen.profile.DietaryPreferencesScreen(
            onDone = { navController.popBackStack() },
            onBack = onBack,
        )
    }

    @Composable
    override fun AddressBookScreen(onBack: () -> Unit) {
        com.nutriplan.android.screen.checkout.AddressBookScreen(onBack = onBack)
    }

    @Composable
    override fun PaymentMethodsScreen(onBack: () -> Unit) {
        val sessionManager = koinInject<SessionManager>()
        com.nutriplan.android.screen.checkout.PaymentMethodsScreen(
            onBack = onBack,
            // The server rejected the session: end it, and SessionGate returns the user to sign-in.
            onSessionExpired = { sessionManager.onSignedOut() },
        )
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

/** Saved-state key: a recommendation was just added to a plan (AIA-604). */
private const val AI_MEAL_ADDED = "ai_meal_added"

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
private fun ProfileScreenContent(onNavigate: (Any) -> Unit) {
    androidx.compose.foundation.layout.Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        androidx.compose.material3.Text("Profile", style = MaterialTheme.typography.headlineLarge)
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
