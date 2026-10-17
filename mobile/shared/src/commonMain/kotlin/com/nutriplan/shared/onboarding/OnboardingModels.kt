package com.nutriplan.shared.onboarding

import com.nutriplan.shared.data.model.DietaryMacroTargets
import com.nutriplan.shared.data.model.UpdateDietaryPreferencesRequest
import kotlinx.serialization.Serializable

/**
 * The ordered steps of the onboarding wizard.
 *
 * The content of each step is built by the platform UI (IDN-602/603/604); the shared layer
 * owns the ordering, progress, and navigation.
 */
@Serializable
enum class OnboardingStep {
    /** Diet type + cuisine preferences (IDN-602). */
    DIET,

    /** Allergies + excluded ingredients (IDN-603). */
    ALLERGIES,

    /** Daily calorie target + macro split (IDN-604). */
    TARGETS,
}

/**
 * Everything the user has entered so far, independent of the step currently shown.
 *
 * Serialized verbatim into the draft so a wizard can be resumed after it is interrupted.
 */
@Serializable
data class OnboardingAnswers(
    val dietType: String? = null,
    val cuisinePreferences: List<String> = emptyList(),
    val allergies: List<String> = emptyList(),
    val excludedIngredients: List<String> = emptyList(),
    val dailyCalorieTarget: Int? = null,
    val macroTargets: DietaryMacroTargets? = null,
    val appetiteSatisfactionLevel: Int? = null,
) {
    /** Map to the wire request; empty collections are omitted rather than sent as `[]`. */
    fun toRequest(): UpdateDietaryPreferencesRequest = UpdateDietaryPreferencesRequest(
        dietType = dietType,
        allergies = allergies.ifEmpty { null },
        dailyCalorieTarget = dailyCalorieTarget,
        macroTargets = macroTargets,
        excludedIngredients = excludedIngredients.ifEmpty { null },
        cuisinePreferences = cuisinePreferences.ifEmpty { null },
        appetiteSatisfactionLevel = appetiteSatisfactionLevel,
    )
}

/** The persisted draft: where the user was and what they had entered. */
@Serializable
data class OnboardingDraft(
    val step: OnboardingStep = OnboardingStep.DIET,
    val answers: OnboardingAnswers = OnboardingAnswers(),
)

/** Immutable state the wizard UI renders. */
data class OnboardingUiState(
    val step: OnboardingStep = OnboardingStep.DIET,
    val answers: OnboardingAnswers = OnboardingAnswers(),
    val isSaving: Boolean = false,
    val error: String? = null,
    val isComplete: Boolean = false,
) {
    private val steps: Int get() = OnboardingStep.entries.size

    /** 1-based position of [step] in the wizard. */
    val stepNumber: Int get() = step.ordinal + 1

    /** Total number of steps. */
    val stepCount: Int get() = steps

    /** Fraction of the wizard completed so far, in `(0, 1]`. */
    val progress: Float get() = stepNumber.toFloat() / steps

    val isFirstStep: Boolean get() = step.ordinal == 0

    val isLastStep: Boolean get() = step.ordinal == steps - 1
}
