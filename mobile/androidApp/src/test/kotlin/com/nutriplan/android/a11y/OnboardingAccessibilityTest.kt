package com.nutriplan.android.a11y

import androidx.compose.ui.test.assert
import androidx.compose.ui.test.assertHeightIsAtLeast
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.screen.onboarding.OnboardingScreen
import com.nutriplan.android.screen.onboarding.OnboardingWizardContent
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.shared.onboarding.OnboardingAnswers
import com.nutriplan.shared.onboarding.OnboardingStep
import com.nutriplan.shared.onboarding.OnboardingUiState
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * IDN-705: accessibility checks for the onboarding screens (intro + post-signup wizard).
 */
@RunWith(AndroidJUnit4::class)
@Config(sdk = [34])
class OnboardingAccessibilityTest {

    @get:Rule
    val compose = createComposeRule()

    private fun renderWizard(state: OnboardingUiState) {
        compose.setContent {
            NutriPlanTheme {
                OnboardingWizardContent(
                    state = state,
                    onUpdateAnswers = {},
                    onBack = {},
                    onNext = {},
                    onSkip = {},
                    onFinish = {},
                )
            }
        }
    }

    @Test
    fun wizard_exposes_step_progress_and_actions() {
        renderWizard(OnboardingUiState(step = OnboardingStep.DIET, answers = OnboardingAnswers()))

        compose.onNodeWithText("Step 1 of 3").assertExists()
        compose.onNodeWithContentDescription("Progress: step 1 of 3").assertExists()
        compose.onNodeWithText("What's your diet?").assert(isHeading())
        compose.onNodeWithText("Skip").assertExists()
        compose.onNodeWithText("Next").assertHeightIsAtLeast(48.dp)
    }

    @Test
    fun wizard_targets_step_exposes_heading_and_calorie_target() {
        renderWizard(
            OnboardingUiState(
                step = OnboardingStep.TARGETS,
                answers = OnboardingAnswers(dailyCalorieTarget = 2000),
            ),
        )

        compose.onNodeWithText("Daily calorie target").assert(isHeading())
        compose.onNodeWithContentDescription("Calorie target: 2000 kilocalories").assertExists()
        compose.onNodeWithText("Finish").assertHeightIsAtLeast(48.dp)
    }

    @Test
    fun intro_screen_exposes_pages_and_navigation() {
        compose.setContent {
            NutriPlanTheme {
                OnboardingScreen(onGetStarted = {})
            }
        }

        compose.onNodeWithText("Skip").assertExists()
        compose.onNodeWithText("Welcome to NutriPlan").assertExists()
        compose.onNodeWithContentDescription("Page 1 of 3, current").assertExists()
        compose.onNodeWithText("Next").assertExists()
    }
}
