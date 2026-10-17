package com.nutriplan.shared.session

import com.nutriplan.shared.data.local.MealPlanCache
import com.nutriplan.shared.data.repository.AuthRepository

/**
 * Ends the user's session: forgets the tokens (including the copy in secure storage) and wipes
 * locally cached personal data, so the next person using the device never sees it.
 */
class SignOut(
    private val authRepository: AuthRepository,
    private val mealPlanCache: MealPlanCache,
) {
    operator fun invoke() {
        // Tokens first: if wiping the cache fails the session is still over.
        authRepository.clearTokens()
        runCatching { mealPlanCache.clear() }
        SessionEvents.emitSignedOut()
    }
}
