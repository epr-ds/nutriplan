package com.nutriplan.shared.session

import com.nutriplan.shared.data.model.UpdateDietaryPreferencesRequest
import com.nutriplan.shared.data.network.ApiException
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertIs

class CompleteOnboardingTest {

    private val veganPreferences = UpdateDietaryPreferencesRequest(
        dietType = "vegan",
        allergies = listOf("peanut"),
        dailyCalorieTarget = 2000,
    )

    @Test
    fun `saves preferences then flips to signed in with the re-fetched profile`() = runTest {
        val repository = FakeIdentityRepository(profile = authResponse(onboardingComplete = true).user)
        val manager = DefaultSessionManager(FakeAuthRepository(), backgroundScope)
        manager.onAuthenticated(authResponse(onboardingComplete = false).user)

        val profile = CompleteOnboarding(repository, manager)(veganPreferences)

        assertEquals(veganPreferences, repository.lastPreferences)
        assertEquals(1, repository.getMeCalls)
        val state = assertIs<SessionState.SignedIn>(manager.state.value)
        assertEquals(profile, state.user)
    }

    @Test
    fun `a failed save stays in onboarding so it can be resumed`() = runTest {
        val repository = FakeIdentityRepository(
            profile = authResponse(onboardingComplete = true).user,
            putError = ApiException.HttpError(statusCode = 500, body = null),
        )
        val manager = DefaultSessionManager(FakeAuthRepository(), backgroundScope)
        manager.onAuthenticated(authResponse(onboardingComplete = false).user)

        assertFailsWith<ApiException.HttpError> {
            CompleteOnboarding(repository, manager)(veganPreferences)
        }

        assertEquals(SessionState.Onboarding, manager.state.value)
        assertEquals(0, repository.getMeCalls)
    }

    @Test
    fun `a failed re-fetch stays in onboarding so it can be resumed`() = runTest {
        val repository = FakeIdentityRepository(
            profile = authResponse(onboardingComplete = true).user,
            getError = ApiException.NetworkError(),
        )
        val manager = DefaultSessionManager(FakeAuthRepository(), backgroundScope)
        manager.onAuthenticated(authResponse(onboardingComplete = false).user)

        assertFailsWith<ApiException> {
            CompleteOnboarding(repository, manager)(veganPreferences)
        }

        assertEquals(SessionState.Onboarding, manager.state.value)
        assertEquals(1, repository.getMeCalls)
    }
}
