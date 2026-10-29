package com.nutriplan.shared.onboarding

import com.nutriplan.shared.session.CompleteOnboarding
import com.nutriplan.shared.session.DefaultSessionManager
import com.nutriplan.shared.session.FakeAuthRepository
import com.nutriplan.shared.session.FakeIdentityRepository
import com.nutriplan.shared.session.authResponse
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull

/** HRD-1004: the first-run onboarding wizard seeds sensible defaults when a step is reached empty. */
class OnboardingWizardDefaultsTest {

    private class Fixture(
        val identity: FakeIdentityRepository,
        val session: DefaultSessionManager,
        val complete: CompleteOnboarding,
    )

    private fun fixture(scope: CoroutineScope): Fixture {
        val identity = FakeIdentityRepository(
            profile = authResponse(onboardingComplete = true).user,
            putError = null,
        )
        val session = DefaultSessionManager(FakeAuthRepository(), scope)
        return Fixture(identity, session, CompleteOnboarding(identity, session))
    }

    @Test
    fun `moving into the targets step seeds the calorie and macro defaults`() = runTest {
        val model = OnboardingViewModel(InMemoryOnboardingDraftStorage(), fixture(this).complete)

        model.next() // DIET -> ALLERGIES
        model.next() // ALLERGIES -> TARGETS

        val answers = model.state.value.answers
        assertNotNull(answers.dailyCalorieTarget, "the targets step must seed a calorie default")
        assertNotNull(answers.macroTargets, "the targets step must seed macro defaults")
    }
}