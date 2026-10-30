package com.nutriplan.android.navigation

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.navigation.NavHostController
import androidx.lifecycle.SavedStateHandle
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.a11y.TestApplication
import com.nutriplan.shared.navigation.Route
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * COM-707: tapping a notification that carries a deep link opens the deep linked screen.
 *
 * The in-app notification center forwards a tap through
 * [AppNavigationScreens.NotificationCenterScreen] into the app deep-link handler, which then opens
 * the deep linked destination (order, plan or meal). Renders the real [AppNavigationGraph] in
 * Robolectric so the wiring under test is the one shipped in the navigation graph itself, not a
 * local copy of it.
 */
@RunWith(AndroidJUnit4::class)
@Config(sdk = [34], application = TestApplication::class)
class NotificationDeepLinkLandingTest {

    @get:Rule
    val compose = createComposeRule()

    private val fakeScreens = FakeAppNavigationScreens()

    @Test
    fun `tapping a notification with an order deep link opens the deep linked screen`() {
        lateinit var navController: NavHostController
        val handledDeepLinks = mutableListOf<String>()

        compose.setContent {
            navController = rememberNavController()
            AppNavigationGraph(
                navController = navController,
                startDestination = Route.NotificationCenter,
                onDeepLink = { deepLink -> handledDeepLinks += deepLink },
                screens = fakeScreens,
            )
        }

        compose.waitForIdle()

        val notificationClick = fakeScreens.notificationClick
        assertTrue(
            "the notification center screen must forward taps into the deep link handler",
            notificationClick != null,
        )

        compose.runOnIdle { notificationClick?.invoke("nutriplan://order/order-789") }
        compose.waitForIdle()

        assertEquals(listOf("nutriplan://order/order-789"), handledDeepLinks)
    }
}

/** Minimal [AppNavigationScreens] double: only the notification center wires its tap handler. */
private class FakeAppNavigationScreens : AppNavigationScreens {

    var notificationClick: ((String) -> Unit)? = null

    @Composable
    override fun NotificationCenterScreen(
        onNavigate: (Any) -> Unit,
        onNotificationClick: (String) -> Unit,
    ) {
        notificationClick = onNotificationClick
    }

    @Composable
    override fun SplashScreen(onNavigate: (Any) -> Unit) {
        Text("SplashScreen")
    }

    @Composable
    override fun OnboardingScreen(onComplete: (Any) -> Unit) {
        Text("OnboardingScreen")
    }

    @Composable
    override fun OnboardingWizardScreen(onComplete: (Any) -> Unit) {
        Text("OnboardingWizardScreen")
    }

    @Composable
    override fun AuthScreen(onLoginSuccess: (Any) -> Unit) {
        Text("AuthScreen")
    }

    @Composable
    override fun MainScreen(onNavigate: (Any) -> Unit) {
        Text("MainScreen")
    }

    @Composable
    override fun MealPlanListScreen(
        onNavigate: (Any) -> Unit,
        onPlanClick: (String) -> Unit,
    ) {
        Text("MealPlanListScreen")
    }

    @Composable
    override fun CreateMealPlanScreen(
        planId: String?,
        onSave: (Any) -> Unit,
        onCancel: () -> Unit,
    ) {
        Text("CreateMealPlanScreen")
    }

    @Composable
    override fun MealPlanDetailScreen(
        planId: String,
        onNavigate: (Any) -> Unit,
        onBack: () -> Unit,
    ) {
        Text("MealPlanDetailScreen")
    }

    @Composable
    override fun RecipeSearchScreen(
        onNavigate: (Any) -> Unit,
        onRecipeClick: (String) -> Unit,
    ) {
        Text("RecipeSearchScreen")
    }

    @Composable
    override fun FavoriteRecipesScreen(onBack: () -> Unit) {
        Text("FavoriteRecipesScreen")
    }

    @Composable
    override fun PickRecipeScreen(planId: String, onBack: () -> Unit) {
        Text("PickRecipeScreen")
    }

    @Composable
    override fun EditMealScreen(
        planId: String,
        mealId: String,
        onBack: () -> Unit,
    ) {
        Text("EditMealScreen")
    }

    @Composable
    override fun AddMealScreen(
        planId: String,
        recipeId: String,
        mealType: String?,
        onBack: () -> Unit,
    ) {
        Text("AddMealScreen")
    }

    @Composable
    override fun PickPlanScreen(
        recipeId: String,
        mealType: String?,
        onBack: () -> Unit,
    ) {
        Text("PickPlanScreen")
    }

    @Composable
    override fun OptimizePlanScreen(planId: String, onBack: () -> Unit) {
        Text("OptimizePlanScreen")
    }

    @Composable
    override fun RecipeDetailScreen(recipeId: String, onBack: () -> Unit) {
        Text("RecipeDetailScreen")
    }

    @Composable
    override fun AiMealAnalysisScreen(onBack: () -> Unit) {
        Text("AiMealAnalysisScreen")
    }

    @Composable
    override fun AiRecommendationsScreen(
        onNavigate: (Any) -> Unit,
        savedState: SavedStateHandle,
    ) {
        Text("AiRecommendationsScreen")
    }

    @Composable
    override fun OrderListScreen(
        onNavigate: (Any) -> Unit,
        onOrderClick: (String) -> Unit,
    ) {
        Text("OrderListScreen")
    }

    @Composable
    override fun OrderDetailScreen(
        orderId: String,
        onBack: () -> Unit,
    ) {
        Text("OrderDetailScreen")
    }

    @Composable
    override fun CheckoutScreen(
        planId: String?,
        reorderOrderId: String?,
        onNavigate: (Any) -> Unit,
        onComplete: (Any) -> Unit,
        onCancel: () -> Unit,
    ) {
        Text("CheckoutScreen")
    }

    @Composable
    override fun NotificationPreferencesScreen(onBack: () -> Unit) {
        Text("NotificationPreferencesScreen")
    }

    @Composable
    override fun ProfileScreen(onNavigate: (Any) -> Unit) {
        Text("ProfileScreen")
    }

    @Composable
    override fun EditProfileScreen(
        onSave: (Any) -> Unit,
        onBack: () -> Unit,
    ) {
        Text("EditProfileScreen")
    }

    @Composable
    override fun DietaryPreferencesScreen(
        onSave: (Any) -> Unit,
        onBack: () -> Unit,
    ) {
        Text("DietaryPreferencesScreen")
    }

    @Composable
    override fun AddressBookScreen(onBack: () -> Unit) {
        Text("AddressBookScreen")
    }

    @Composable
    override fun PaymentMethodsScreen(onBack: () -> Unit) {
        Text("PaymentMethodsScreen")
    }

    @Composable
    override fun DeepLinkMealScreen(
        mealId: String,
        onBack: () -> Unit,
    ) {
        Text("DeepLinkMealScreen")
    }

    @Composable
    override fun DeepLinkPlanScreen(
        planId: String,
        onBack: () -> Unit,
    ) {
        Text("DeepLinkPlanScreen")
    }

    @Composable
    override fun DeepLinkOrderScreen(
        orderId: String,
        onBack: () -> Unit,
    ) {
        Text("DeepLinkOrderScreen")
    }
}