package com.nutriplan.shared.session

import com.nutriplan.shared.data.model.UpdateDietaryPreferencesRequest
import com.nutriplan.shared.data.model.UserProfile
import com.nutriplan.shared.data.repository.IdentityRepository

/**
 * Persist the onboarding preferences and finish onboarding.
 *
 * The preferences are written first (`PUT /users/me/dietary-preferences`), then the profile is
 * re-read from the server (`GET /users/me`) so the session carries the canonical, normalized
 * values — the client never guesses what the server stored. Only when both calls succeed does the
 * session flip to [SessionState.SignedIn].
 *
 * The flow is resumable: any failure propagates and the session stays in [SessionState.Onboarding],
 * so the caller can simply invoke this again (the PUT is idempotent).
 */
class CompleteOnboarding(
    private val identityRepository: IdentityRepository,
    private val sessionManager: SessionManager,
) {
    suspend operator fun invoke(preferences: UpdateDietaryPreferencesRequest): UserProfile {
        identityRepository.updateDietaryPreferences(preferences)
        val profile = identityRepository.getMe()
        sessionManager.onOnboardingCompleted(profile)
        return profile
    }
}
