package com.nutriplan.shared.session

import com.nutriplan.shared.data.model.UserProfile

/**
 * The app's session, as observed by navigation and the UI.
 *
 * - [SignedOut]: no valid tokens; the app shows the auth flow.
 * - [Onboarding]: authenticated, but the user has not finished onboarding (no dietary
 *   preferences saved yet); the app shows the onboarding flow (IDN-507).
 * - [SignedIn]: authenticated and onboarded; the app shows the main graph.
 */
sealed interface SessionState {

    /** No valid session; show login/register. */
    data object SignedOut : SessionState

    /** Authenticated but onboarding is incomplete; show the onboarding flow. */
    data object Onboarding : SessionState

    /** Fully signed in; the [user] is the latest profile we have seen. */
    data class SignedIn(val user: UserProfile) : SessionState
}
