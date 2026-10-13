import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.navigation.compose.rememberNavController
import com.nutriplan.android.screen.auth.LoginScreen
import com.nutriplan.android.screen.checkout.CheckoutScreen
import com.nutriplan.android.screen.home.HomeScreen
import com.nutriplan.android.screen.onboarding.OnboardingScreen
import com.nutriplan.android.screen.profile.ProfileScreen
import com.nutriplan.shared.navigation.AppNavigationGraph
import com.nutriplan.shared.navigation.Route
import com.nutriplan.shared.ui.theme.NutriPlanTheme

/**
 * Main activity entry point for the NutriPlan Android app.
 *
 * Sets up the Compose navigation graph and applies the NutriPlan theme.
 */
class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            NutriPlanTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    val navController = rememberNavController()
                    AppNavigationGraph(
                        navController = navController,
                        startDestination = Route.Splash,
                        screens = remember(navController) { MainNavigationScreens(navController) },
                    )
                }
            }
        }
    }
}

/**
 * Concrete implementation of [AppNavigationScreens] for the Android app.
 *
 * Each screen composable is implemented with actual UI components.
 */
class MainNavigationScreens(private val navController: androidx.navigation.NavHostController) :
    com.nutriplan.shared.navigation.AppNavigationScreens {

    @Composable
    override fun SplashScreen(onNavigate: (Any) -> Unit) {
        SplashScreenContent(onNavigate)
    }

    @Composable
    override fun OnboardingScreen(onComplete: (Any) -> Unit) {
        OnboardingScreen(onComplete)
    }

    @Composable
    override fun AuthScreen(onLoginSuccess: (Any) -> Unit) {
        LoginScreen(
            onLoginSuccess = { onLoginSuccess(Route.Main) },
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
        ProfileScreen(
            onNavigateToEditProfile = { onNavigate(Route.EditProfile) },
            onNavigateToDietaryPreferences = { onNavigate(Route.DietaryPreferences) },
            onNavigateToOrderHistory = { onNavigate(Route.OrderList) },
            onNavigateToNotificationSettings = { onNavigate(Route.NotificationCenter) },
            onLogout = { onNavigate(Route.Auth) }
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
private fun SplashScreen(onNavigate: (Any) -> Unit) {
    androidx.compose.foundation.layout.Box(
        modifier = androidx.compose.foundation.layout.fillMaxSize(),
        contentAlignment = androidx.compose.foundation.layout.Alignment.Center,
    ) {
        androidx.compose.material3.Text("Splash", style = androidx.compose.material3.Typography.headlineLarge)
    }
}

@Composable
private fun OnboardingScreenContent(onComplete: (Any) -> Unit) {
    androidx.compose.foundation.layout.Box(
        modifier = androidx.compose.foundation.layout.fillMaxSize(),
        contentAlignment = androidx.compose.foundation.layout.Alignment.Center,
    ) {
        androidx.compose.material3.Text("Onboarding", style = androidx.compose.material3.Typography.headlineLarge)
    }
}

@Composable
private fun AuthScreenContent(onLoginSuccess: (Any) -> Unit) {
    androidx.compose.foundation.layout.Box(
        modifier = androidx.compose.foundation.layout.fillMaxSize(),
        contentAlignment = androidx.compose.foundation.layout.Alignment.Center,
    ) {
        androidx.compose.material3.Text("Auth", style = androidx.compose.material3.Typography.headlineLarge)
    }
}

@Composable
private fun MainScreenContent(onNavigate: (Any) -> Unit) {
    androidx.compose.foundation.layout.Box(
        modifier = androidx.compose.foundation.layout.fillMaxSize(),
        contentAlignment = androidx.compose.foundation.layout.Alignment.Center,
    ) {
        androidx.compose.material3.Text("Main", style = androidx.compose.material3.Typography.headlineLarge)
    }
}

@Composable
private fun MealPlanListScreenContent(
    onNavigate: (Any) -> Unit,
    onPlanClick: (String) -> Unit,
) {
    androidx.compose.foundation.layout.Box(
        modifier = androidx.compose.foundation.layout.fillMaxSize(),
        contentAlignment = androidx.compose.foundation.layout.Alignment.Center,
    ) {
        androidx.compose.material3.Text("Meal Plans", style = androidx.compose.material3.Typography.headlineLarge)
    }
}

@Composable
private fun CreateMealPlanScreenContent(
    planId: String?,
    onSave: (Any) -> Unit,
    onCancel: () -> Unit,
) {
    androidx.compose.foundation.layout.Box(
        modifier = androidx.compose.foundation.layout.fillMaxSize(),
        contentAlignment = androidx.compose.foundation.layout.Alignment.Center,
    ) {
        androidx.compose.material3.Text("Create Plan", style = androidx.compose.material3.Typography.headlineLarge)
    }
}

@Composable
private fun MealPlanDetailScreenContent(
    planId: String,
    onNavigate: (Any) -> Unit,
    onBack: () -> Unit,
) {
    androidx.compose.foundation.layout.Box(
        modifier = androidx.compose.foundation.layout.fillMaxSize(),
        contentAlignment = androidx.compose.foundation.layout.Alignment.Center,
    ) {
        androidx.compose.material3.Text("Plan Detail: $planId", style = androidx.compose.material3.Typography.headlineLarge)
    }
}

@Composable
private fun RecipeSearchScreenContent(
    onNavigate: (Any) -> Unit,
    onRecipeClick: (String) -> Unit,
) {
    androidx.compose.foundation.layout.Box(
        modifier = androidx.compose.foundation.layout.fillMaxSize(),
        contentAlignment = androidx.compose.foundation.layout.Alignment.Center,
    ) {
        androidx.compose.material3.Text("Recipes", style = androidx.compose.material3.Typography.headlineLarge)
    }
}

@Composable
private fun RecipeDetailScreenContent(recipeId: String, onBack: () -> Unit) {
    androidx.compose.foundation.layout.Box(
        modifier = androidx.compose.foundation.layout.fillMaxSize(),
        contentAlignment = androidx.compose.foundation.layout.Alignment.Center,
    ) {
        androidx.compose.material3.Text("Recipe: $recipeId", style = androidx.compose.material3.Typography.headlineLarge)
    }
}

@Composable
private fun AiMealAnalysisScreenContent(
    onNavigate: (Any) -> Unit,
    onResult: (com.nutriplan.shared.domain.Resource<*>) -> Unit,
) {
    androidx.compose.foundation.layout.Box(
        modifier = androidx.compose.foundation.layout.fillMaxSize(),
        contentAlignment = androidx.compose.foundation.layout.Alignment.Center,
    ) {
        androidx.compose.material3.Text("AI Analysis", style = androidx.compose.material3.Typography.headlineLarge)
    }
}

@Composable
private fun AiRecommendationsScreenContent(onNavigate: (Any) -> Unit) {
    androidx.compose.foundation.layout.Box(
        modifier = androidx.compose.foundation.layout.fillMaxSize(),
        contentAlignment = androidx.compose.foundation.layout.Alignment.Center,
    ) {
        androidx.compose.material3.Text("AI Recommendations", style = androidx.compose.material3.Typography.headlineLarge)
    }
}

@Composable
private fun OrderListScreenContent(
    onNavigate: (Any) -> Unit,
    onOrderClick: (String) -> Unit,
) {
    androidx.compose.foundation.layout.Box(
        modifier = androidx.compose.foundation.layout.fillMaxSize(),
        contentAlignment = androidx.compose.foundation.layout.Alignment.Center,
    ) {
        androidx.compose.material3.Text("Orders", style = androidx.compose.material3.Typography.headlineLarge)
    }
}

@Composable
private fun OrderDetailScreenContent(orderId: String, onBack: () -> Unit) {
    androidx.compose.foundation.layout.Box(
        modifier = androidx.compose.foundation.layout.fillMaxSize(),
        contentAlignment = androidx.compose.foundation.layout.Alignment.Center,
    ) {
        androidx.compose.material3.Text("Order: $orderId", style = androidx.compose.material3.Typography.headlineLarge)
    }
}

@Composable
private fun CheckoutScreenContent(
    onNavigate: (Any) -> Unit,
    onComplete: (Any) -> Unit,
    onCancel: () -> Unit,
) {
    androidx.compose.foundation.layout.Box(
        modifier = androidx.compose.foundation.layout.fillMaxSize(),
        contentAlignment = androidx.compose.foundation.layout.Alignment.Center,
    ) {
        androidx.compose.material3.Text("Checkout", style = androidx.compose.material3.Typography.headlineLarge)
    }
}

@Composable
private fun NotificationCenterScreenContent(
    onNavigate: (Any) -> Unit,
    onNotificationClick: (String) -> Unit,
) {
    androidx.compose.foundation.layout.Box(
        modifier = androidx.compose.foundation.layout.fillMaxSize(),
        contentAlignment = androidx.compose.foundation.layout.Alignment.Center,
    ) {
        androidx.compose.material3.Text("Notifications", style = androidx.compose.material3.Typography.headlineLarge)
    }
}

@Composable
private fun ProfileScreenContent(onNavigate: (Any) -> Unit) {
    androidx.compose.foundation.layout.Box(
        modifier = androidx.compose.foundation.layout.fillMaxSize(),
        contentAlignment = androidx.compose.foundation.layout.Alignment.Center,
    ) {
        androidx.compose.material3.Text("Profile", style = androidx.compose.material3.Typography.headlineLarge)
    }
}

@Composable
private fun EditProfileScreenContent(
    onSave: (Any) -> Unit,
    onBack: () -> Unit,
) {
    androidx.compose.foundation.layout.Box(
        modifier = androidx.compose.foundation.layout.fillMaxSize(),
        contentAlignment = androidx.compose.foundation.layout.Alignment.Center,
    ) {
        androidx.compose.material3.Text("Edit Profile", style = androidx.compose.material3.Typography.headlineLarge)
    }
}

@Composable
private fun DietaryPreferencesScreenContent(
    onSave: (Any) -> Unit,
    onBack: () -> Unit,
) {
    androidx.compose.foundation.layout.Box(
        modifier = androidx.compose.foundation.layout.fillMaxSize(),
        contentAlignment = androidx.compose.foundation.layout.Alignment.Center,
    ) {
        androidx.compose.material3.Text("Dietary Preferences", style = androidx.compose.material3.Typography.headlineLarge)
    }
}

@Composable
private fun DeepLinkMealScreenContent(mealId: String, onBack: () -> Unit) {
    androidx.compose.foundation.layout.Box(
        modifier = androidx.compose.foundation.layout.fillMaxSize(),
        contentAlignment = androidx.compose.foundation.layout.Alignment.Center,
    ) {
        androidx.compose.material3.Text("Meal: $mealId", style = androidx.compose.material3.Typography.headlineLarge)
    }
}

@Composable
private fun DeepLinkPlanScreenContent(planId: String, onBack: () -> Unit) {
    androidx.compose.foundation.layout.Box(
        modifier = androidx.compose.foundation.layout.fillMaxSize(),
        contentAlignment = androidx.compose.foundation.layout.Alignment.Center,
    ) {
        androidx.compose.material3.Text("Plan: $planId", style = androidx.compose.material3.Typography.headlineLarge)
    }
}

@Composable
private fun DeepLinkOrderScreenContent(orderId: String, onBack: () -> Unit) {
    androidx.compose.foundation.layout.Box(
        modifier = androidx.compose.foundation.layout.fillMaxSize(),
        contentAlignment = androidx.compose.foundation.layout.Alignment.Center,
    ) {
        androidx.compose.material3.Text("Order: $orderId", style = androidx.compose.material3.Typography.headlineLarge)
    }
}