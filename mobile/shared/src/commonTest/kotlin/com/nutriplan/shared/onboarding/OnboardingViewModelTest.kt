package com.nutriplan.shared.onboarding

import com.nutriplan.shared.data.model.DietaryMacroTargets
import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.session.CompleteOnboarding
import com.nutriplan.shared.session.DefaultSessionManager
import com.nutriplan.shared.session.FakeAuthRepository
import com.nutriplan.shared.session.FakeIdentityRepository
import com.nutriplan.shared.session.SessionState
import com.nutriplan.shared.session.authResponse
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class OnboardingViewModelTest {

    private class Fixture(
        val identity: FakeIdentityRepository,
        val session: DefaultSessionManager,
        val complete: CompleteOnboarding,
    )

    private fun fixture(
        scope: CoroutineScope,
        putError: Throwable? = null,
    ): Fixture {
        val identity = FakeIdentityRepository(
            profile = authResponse(onboardingComplete = true).user,
            putError = putError,
        )
        val session = DefaultSessionManager(FakeAuthRepository(), scope)
        return Fixture(identity, session, CompleteOnboarding(identity, session))
    }

    @Test
    fun `starts on the first step with an empty draft`() = runTest {
        val model = OnboardingViewModel(InMemoryOnboardingDraftStorage(), fixture(backgroundScope).complete)

        val state = model.state.value
        assertEquals(OnboardingStep.DIET, state.step)
        assertEquals(1, state.stepNumber)
        assertEquals(3, state.stepCount)
        assertTrue(state.isFirstStep)
        assertFalse(state.isLastStep)
        assertEquals(1f / 3f, state.progress, absoluteTolerance = 0.001f)
    }

    @Test
    fun `next and back move through the steps and progress`() = runTest {
        val model = OnboardingViewModel(InMemoryOnboardingDraftStorage(), fixture(backgroundScope).complete)

        assertTrue(model.next())
        assertEquals(OnboardingStep.ALLERGIES, model.state.value.step)
        assertEquals(2f / 3f, model.state.value.progress, absoluteTolerance = 0.001f)

        assertTrue(model.next())
        assertEquals(OnboardingStep.TARGETS, model.state.value.step)
        assertTrue(model.state.value.isLastStep)

        // No further step to advance to, but we can go back.
        assertFalse(model.next())
        assertTrue(model.back())
        assertEquals(OnboardingStep.ALLERGIES, model.state.value.step)
    }

    @Test
    fun `back on the first step is a no-op`() = runTest {
        val model = OnboardingViewModel(InMemoryOnboardingDraftStorage(), fixture(backgroundScope).complete)

        assertFalse(model.back())
        assertEquals(OnboardingStep.DIET, model.state.value.step)
    }

    @Test
    fun `skipping advances without requiring any answers`() = runTest {
        val model = OnboardingViewModel(InMemoryOnboardingDraftStorage(), fixture(backgroundScope).complete)

        assertTrue(model.next())

        assertEquals(OnboardingStep.ALLERGIES, model.state.value.step)
        assertEquals(OnboardingAnswers(), model.state.value.answers)
    }

    @Test
    fun `changes are persisted so the wizard can be resumed`() = runTest {
        val storage = InMemoryOnboardingDraftStorage()
        val model = OnboardingViewModel(storage, fixture(backgroundScope).complete)
        model.updateAnswers(OnboardingAnswers(dietType = "vegan"))
        model.next()

        // A fresh wizard over the same storage picks up where the previous one left off.
        val resumed = OnboardingViewModel(storage, fixture(backgroundScope).complete)
        assertEquals(OnboardingStep.ALLERGIES, resumed.state.value.step)
        assertEquals("vegan", resumed.state.value.answers.dietType)
    }

    @Test
    fun `finishing persists preferences, clears the draft, and flips the session`() = runTest {
        val storage = InMemoryOnboardingDraftStorage()
        val fx = fixture(backgroundScope)
        val model = OnboardingViewModel(storage, fx.complete)
        model.updateAnswers(
            OnboardingAnswers(
                dietType = "vegan",
                allergies = listOf("peanut"),
                cuisinePreferences = listOf("mexican"),
                dailyCalorieTarget = 2000,
                macroTargets = DietaryMacroTargets(proteinGrams = 120),
            ),
        )

        assertTrue(model.finish())

        val saved = assertNotNull(fx.identity.lastPreferences)
        assertEquals("vegan", saved.dietType)
        assertEquals(listOf("peanut"), saved.allergies)
        assertEquals(2000, saved.dailyCalorieTarget)
        assertTrue(model.state.value.isComplete)
        assertFalse(model.state.value.isSaving)
        assertNull(storage.loadDraft())
        assertIs<SessionState.SignedIn>(fx.session.state.value)
    }

    @Test
    fun `a failed save stays on the step, keeps the draft, and reports the error`() = runTest {
        val storage = InMemoryOnboardingDraftStorage()
        val fx = fixture(backgroundScope, putError = ApiException.HttpError(statusCode = 500, body = null))
        val model = OnboardingViewModel(storage, fx.complete)
        model.updateAnswers(OnboardingAnswers(dietType = "vegan"))
        model.next()
        model.next()

        assertFalse(model.finish())

        assertEquals(OnboardingStep.TARGETS, model.state.value.step)
        assertNotNull(model.state.value.error)
        assertFalse(model.state.value.isComplete)
        assertNotNull(storage.loadDraft())
        assertEquals(SessionState.SignedOut, fx.session.state.value)
    }

    @Test
    fun `a malformed stored draft is ignored instead of crashing`() = runTest {
        val storage = InMemoryOnboardingDraftStorage(initial = "{not json")

        val model = OnboardingViewModel(storage, fixture(backgroundScope).complete)

        assertEquals(OnboardingStep.DIET, model.state.value.step)
    }

    @Test
    fun `finish propagates cancellation instead of swallowing it`() = runTest {
        val storage = InMemoryOnboardingDraftStorage()
        val fx = fixture(backgroundScope, putError = kotlinx.coroutines.CancellationException("cancelled"))
        val model = OnboardingViewModel(storage, fx.complete)

        assertFailsWith<kotlinx.coroutines.CancellationException> { model.finish() }

        assertFalse(model.state.value.isSaving)
    }
}
