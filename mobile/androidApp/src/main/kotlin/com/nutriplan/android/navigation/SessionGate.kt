package com.nutriplan.android.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.navigation.NavDestination
import androidx.navigation.NavDestination.Companion.hasRoute
import androidx.navigation.NavHostController
import androidx.navigation.compose.currentBackStackEntryAsState
import com.nutriplan.shared.navigation.Route
import com.nutriplan.shared.session.SessionState

/**
 * DPL-509: session-gated routing for every screen behind the login.
 *
 * Whenever the session ends while the user is on a screen that needs it (a rejected token refresh,
 * an expired session, a sign-out from another screen), they are sent to the auth flow and the back
 * stack is cleared so Back cannot return to signed-in content. The splash, onboarding intro and auth
 * screens are public: they are never redirected.
 */
@Composable
fun SessionGate(navController: NavHostController, sessionState: SessionState) {
    val entry by navController.currentBackStackEntryAsState()
    val destination = entry?.destination

    LaunchedEffect(sessionState, destination) {
        if (sessionState == SessionState.SignedOut && destination != null && destination.requiresSession()) {
            navController.navigate(Route.Auth) {
                popUpTo(navController.graph.id) { inclusive = true }
            }
        }
    }
}

/** Screens a signed-out user may see; everything else requires a session. */
internal fun NavDestination.requiresSession(): Boolean =
    !(hasRoute<Route.Splash>() || hasRoute<Route.Onboarding>() || hasRoute<Route.Auth>())
