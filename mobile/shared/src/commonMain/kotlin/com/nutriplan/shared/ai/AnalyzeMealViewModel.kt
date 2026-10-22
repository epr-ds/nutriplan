package com.nutriplan.shared.ai

import com.nutriplan.shared.data.model.MealAnalysis
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlin.coroutines.cancellation.CancellationException

/**
 * Observable state of the analyze-meal quick action (AIA-607).
 *
 * [result] is the analysis of [analyzedDescription], which may differ from [description] once the
 * user starts editing again.
 */
data class AnalyzeMealUiState(
    val description: String = "",
    /** The user asked for an analysis without describing a meal. */
    val descriptionMissing: Boolean = false,
    val isAnalyzing: Boolean = false,
    val result: MealAnalysis? = null,
    val analyzedDescription: String? = null,
    val error: AiError? = null,
) {
    /** The description can be sent: there is text and no analysis is running. */
    val canAnalyze: Boolean get() = !isAnalyzing && description.isNotBlank()
}

/**
 * Shared logic of the analyze-meal quick action (AIA-607), used by the Compose and SwiftUI screens:
 * the user describes a meal in words and gets its estimated nutrition, how it fits their targets
 * and any warnings, through the AI Advisor's analyze-meal endpoint.
 *
 * - A blank description is never sent; the form says what is missing instead.
 * - A newer request makes an older one irrelevant: its answer is dropped.
 * - A failure clears the previous analysis rather than showing it next to the error.
 *
 * The functions are `suspend` so the UI owns the coroutine scope; [CancellationException] is
 * rethrown so leaving the screen cancels cleanly.
 */
class AnalyzeMealViewModel(private val advisor: AiAdvisor) {

    private val _state = MutableStateFlow(AnalyzeMealUiState())
    val state: StateFlow<AnalyzeMealUiState> = _state.asStateFlow()

    /** Identifies the latest request; answers to older ones are ignored. */
    private var generation = 0

    fun onDescriptionChange(value: String) {
        _state.update { it.copy(description = value.take(MAX_DESCRIPTION_LENGTH), descriptionMissing = false) }
    }

    /** Analyze the meal as described now; also the retry after a failure. */
    suspend fun analyze() {
        val description = _state.value.description.trim()
        if (description.isEmpty()) {
            _state.update { it.copy(descriptionMissing = true) }
            return
        }
        val token = ++generation
        _state.update { it.copy(isAnalyzing = true, error = null, descriptionMissing = false) }
        try {
            val outcome = advisor.analyzeMeal(description)
            if (token != generation) return
            _state.update { state ->
                when (outcome) {
                    is AiResult.Success -> state.copy(
                        isAnalyzing = false,
                        result = outcome.value,
                        analyzedDescription = description,
                    )
                    is AiResult.Failure -> state.copy(
                        isAnalyzing = false,
                        result = null,
                        analyzedDescription = null,
                        error = outcome.error,
                    )
                }
            }
        } catch (e: CancellationException) {
            if (token == generation) _state.update { it.copy(isAnalyzing = false) }
            throw e
        }
    }

    companion object {
        /** A meal description is a sentence or two; longer text is cut. */
        const val MAX_DESCRIPTION_LENGTH = 500
    }
}
