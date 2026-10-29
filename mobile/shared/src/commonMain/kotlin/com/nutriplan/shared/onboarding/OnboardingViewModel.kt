package com.nutriplan.shared.onboarding

import com.nutriplan.shared.session.CompleteOnboarding
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.json.Json

/**
 * Drives the onboarding wizard: step navigation, progress, skipping, and resuming.
 *
 * This is the shared "ViewModel" the platform UIs (Compose/SwiftUI) bind to. It owns the current
 * [OnboardingUiState] and mirrors it into an [OnboardingDraftStorage] on every change, so an
 * interrupted wizard is restored where the user left off. Finishing hands the collected answers to
 * [CompleteOnboarding], which persists them, re-reads the profile, and flips the session.
 *
 * [finish] is a suspend function rather than launching its own coroutine so the caller owns the
 * lifecycle (a screen can cancel it when it leaves) and tests stay deterministic.
 */
class OnboardingViewModel(
    private val draftStorage: OnboardingDraftStorage,
    private val completeOnboarding: CompleteOnboarding,
) {

    private val json = Json { ignoreUnknownKeys = true }

    private val _state = MutableStateFlow(restore())

    /** The current wizard state; collect it to render. */
    val state: StateFlow<OnboardingUiState> = _state.asStateFlow()

    private fun restore(): OnboardingUiState {
        val draft = draftStorage.loadDraft()?.let { encoded ->
            runCatching { json.decodeFromString(OnboardingDraft.serializer(), encoded) }.getOrNull()
        } ?: return OnboardingUiState()
        return OnboardingUiState(step = draft.step, answers = draft.answers)
    }

    /** Replace the answers wholesale and persist the draft. */
    fun updateAnswers(answers: OnboardingAnswers) {
        _state.value = _state.value.copy(answers = answers, error = null)
        persist()
    }

    /**
     * Move to the next step. Returns false when already on the last step, so the caller can call
     * [finish] instead. Skips are just [next] without requiring input.
     */
    fun next(): Boolean = move(+1)

    /** Move to the previous step. Returns false when already on the first step. */
    fun back(): Boolean = move(-1)

    private fun move(delta: Int): Boolean {
        val current = _state.value
        val target = current.step.ordinal + delta
        if (target !in OnboardingStep.entries.indices) return false
        val answers = if (target == OnboardingStep.TARGETS && current.answers.dailyCalorieTarget == null) {
            current.answers.copy(
                dailyCalorieTarget = MacroCalculator.DEFAULT_CALORIES,
                macroTargets = MacroCalculator.defaultMacroTargets(MacroCalculator.DEFAULT_CALORIES),
            )
        } else {
            current.answers
        }
        _state.value = current.copy(step = OnboardingStep.entries[target], answers = answers, error = null)
        persist()
        return true
    }

    /**
     * Persist the answers and finish onboarding.
     *
     * Returns true on success (the session flips to signed in and the draft is cleared). On
     * failure the wizard stays on the last step with [OnboardingUiState.error] set and the draft
     * intact, so the user can simply try again.
     */
    suspend fun finish(): Boolean {
        _state.value = _state.value.copy(isSaving = true, error = null)
        return try {
            completeOnboarding(_state.value.answers.toRequest())
            draftStorage.clearDraft()
            _state.value = _state.value.copy(isSaving = false, isComplete = true)
            true
        } catch (cancellation: CancellationException) {
            _state.value = _state.value.copy(isSaving = false)
            throw cancellation
        } catch (failure: Exception) {
            _state.value = _state.value.copy(isSaving = false, error = OnboardingError.SAVE_FAILED)
            false
        }
    }

    private fun persist() {
        val current = _state.value
        val draft = OnboardingDraft(step = current.step, answers = current.answers)
        draftStorage.saveDraft(json.encodeToString(OnboardingDraft.serializer(), draft))
    }
}
