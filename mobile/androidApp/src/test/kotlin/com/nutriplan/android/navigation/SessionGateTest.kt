package com.nutriplan.android.navigation

import androidx.compose.material3.Text
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.a11y.TestApplication
import com.nutriplan.shared.data.model.UserProfile
import com.nutriplan.shared.navigation.Route
import com.nutriplan.shared.session.SessionState
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * DPL-509: leaving signed-in screens when the session ends, and never bouncing public screens.
 */
@RunWith(AndroidJUnit4::class)
@Config(sdk = [34], application = TestApplication::class)
class SessionGateTest {

    @get:Rule
    val compose = createComposeRule()

    private val user = UserProfile(id = "u1", email = "ana@example.com", firstName = "Ana", lastName = "Perez")

    private var sessionState: SessionState by mutableStateOf(SessionState.SignedIn(user))
    private lateinit var navController: NavHostController

    private fun render(start: Any) {
        compose.setContent {
            navController = rememberNavController()
            SessionGate(navController, sessionState)
            NavHost(navController, startDestination = start) {
                composable<Route.Splash> { Text("splash") }
                composable<Route.Auth> { Text("auth") }
                composable<Route.Onboarding> { Text("onboarding") }
                composable<Route.Main> { Text("main") }
                composable<Route.MealPlanList> { Text("plans") }
            }
        }
    }

    @Test
    fun `a signed in user stays on a signed in screen`() {
        render(Route.MealPlanList)

        compose.waitForIdle()
        compose.onNodeWithText("plans").assertExists()
    }

    @Test
    fun `ending the session on a signed in screen sends the user to auth`() {
        render(Route.MealPlanList)

        compose.runOnIdle { sessionState = SessionState.SignedOut }
        compose.waitForIdle()

        compose.onNodeWithText("auth").assertExists()
        compose.onNodeWithText("plans").assertDoesNotExist()
    }

    @Test
    fun `the back stack is cleared so back cannot return to signed in content`() {
        render(Route.Main)
        compose.runOnIdle { navController.navigate(Route.MealPlanList) }
        compose.waitForIdle()

        compose.runOnIdle { sessionState = SessionState.SignedOut }
        compose.waitForIdle()

        compose.onNodeWithText("auth").assertExists()
        assertNull(navController.previousBackStackEntry)
    }

    @Test
    fun `a signed out user on the auth screen is left alone`() {
        sessionState = SessionState.SignedOut
        render(Route.Auth)

        compose.waitForIdle()
        compose.onNodeWithText("auth").assertExists()
    }

    @Test
    fun `splash and the onboarding intro are public`() {
        sessionState = SessionState.SignedOut
        render(Route.Splash)
        compose.waitForIdle()
        compose.onNodeWithText("splash").assertExists()

        compose.runOnIdle { navController.navigate(Route.Onboarding) }
        compose.waitForIdle()
        compose.onNodeWithText("onboarding").assertExists()
    }
}
