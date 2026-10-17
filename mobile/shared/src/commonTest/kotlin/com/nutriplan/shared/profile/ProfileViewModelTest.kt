package com.nutriplan.shared.profile

import com.nutriplan.shared.data.model.UpdateDietaryPreferencesRequest
import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.session.DefaultSessionManager
import com.nutriplan.shared.session.FakeAuthRepository
import com.nutriplan.shared.session.SessionState
import com.nutriplan.shared.session.authResponse
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class ProfileViewModelTest {

    private class Fixture(
        val model: ProfileViewModel,
        val repository: FakeProfileIdentityRepository,
        val session: DefaultSessionManager,
    )

    private fun fixture(
        scope: CoroutineScope,
        getError: Throwable? = null,
        saveError: Throwable? = null,
    ): Fixture {
        val repository = FakeProfileIdentityRepository(
            profile = authResponse(onboardingComplete = true).user,
            getError = getError,
            saveError = saveError,
        )
        val session = DefaultSessionManager(FakeAuthRepository(), scope)
        return Fixture(ProfileViewModel(repository, session), repository, session)
    }

    @Test
    fun `load populates the profile and syncs the session`() = runTest {
        val fx = fixture(backgroundScope)

        assertTrue(fx.model.load())

        val state = fx.model.state.value
        assertEquals("Ana", state.profile?.name)
        assertFalse(state.isLoading)
        assertNull(state.loadError)
        val session = assertIs<SessionState.SignedIn>(fx.session.state.value)
        assertEquals("Ana", session.user.name)
    }

    @Test
    fun `load failure surfaces an error and leaves the profile empty`() = runTest {
        val fx = fixture(backgroundScope, getError = ApiException.NetworkError())

        assertFalse(fx.model.load())

        val state = fx.model.state.value
        assertNull(state.profile)
        assertNotNull(state.loadError)
        assertFalse(state.isLoading)
    }

    @Test
    fun `saveName trims, updates the profile, and flags success`() = runTest {
        val fx = fixture(backgroundScope)

        assertTrue(fx.model.saveName("  Ana María  "))

        assertEquals("Ana María", fx.repository.lastProfileRequest?.name)
        assertEquals("Ana María", fx.model.state.value.profile?.name)
        assertTrue(fx.model.state.value.isSaved)
        assertFalse(fx.model.state.value.isSaving)
    }

    @Test
    fun `an empty name is rejected without a request`() = runTest {
        val fx = fixture(backgroundScope)

        assertFalse(fx.model.saveName("   "))

        assertNull(fx.repository.lastProfileRequest)
        assertEquals("Enter your name.", fx.model.state.value.saveError)
    }

    @Test
    fun `savePreferences forwards the request and reflects the refreshed profile`() = runTest {
        val fx = fixture(backgroundScope)
        val request = UpdateDietaryPreferencesRequest(dietType = "vegan", dailyCalorieTarget = 1800)

        assertTrue(fx.model.savePreferences(request))

        assertEquals(request, fx.repository.lastPreferences)
        assertTrue(fx.model.state.value.isSaved)
        assertIs<SessionState.SignedIn>(fx.session.state.value)
    }

    @Test
    fun `updateAvatar uploads the bytes and refreshes the avatar url`() = runTest {
        val fx = fixture(backgroundScope)

        assertTrue(fx.model.updateAvatar("image/png", byteArrayOf(1, 2, 3)))

        assertEquals("image/png", fx.repository.lastAvatar?.first)
        assertContentEquals(byteArrayOf(1, 2, 3), fx.repository.lastAvatar?.second)
        assertEquals("https://cdn.example.com/avatar.png", fx.model.state.value.profile?.avatarUrl)
    }

    @Test
    fun `a failed save surfaces an error and is not flagged successful`() = runTest {
        val fx = fixture(backgroundScope, saveError = ApiException.HttpError(500, null))

        assertFalse(fx.model.saveName("Ana"))

        val state = fx.model.state.value
        assertNotNull(state.saveError)
        assertFalse(state.isSaved)
        assertFalse(state.isSaving)
    }

    @Test
    fun `consumeSaved clears the transient success flag`() = runTest {
        val fx = fixture(backgroundScope)
        fx.model.saveName("Ana")
        assertTrue(fx.model.state.value.isSaved)

        fx.model.consumeSaved()

        assertFalse(fx.model.state.value.isSaved)
    }

    @Test
    fun `save propagates cancellation`() = runTest {
        val fx = fixture(backgroundScope, saveError = CancellationException("cancelled"))

        assertFailsWith<CancellationException> { fx.model.saveName("Ana") }

        assertFalse(fx.model.state.value.isSaving)
    }
}
