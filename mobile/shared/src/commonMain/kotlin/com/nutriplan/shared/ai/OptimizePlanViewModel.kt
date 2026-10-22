package com.nutriplan.shared.ai

import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.model.NutritionalInfo
import com.nutriplan.shared.data.model.UpdateMealRequest
import com.nutriplan.shared.data.repository.DietaryRepository
import com.nutriplan.shared.planning.IsoDate
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlin.coroutines.cancellation.CancellationException

/**
 * How one meal of the plan changes in an optimized draft. Optimization only adjusts the servings of
 * the plan's existing meals (the draft keeps their ids), so this is the whole difference.
 */
data class MealServingChange(
    val mealId: String,
    /** `breakfast`, `lunch`, `dinner` or `snack`. */
    val mealType: String,
    /** The recipe's name when the plan knows it. */
    val recipeName: String?,
    /** The meal's day (ISO `yyyy-MM-dd`), or null when it has none. */
    val date: String?,
    val before: Double,
    val after: Double,
)

/** Observable state of the optimize-plan flow (AIA-605). */
data class OptimizePlanUiState(
    /** One of [AiAdvisor.GOALS]. */
    val goal: String = AiAdvisor.GOALS.first(),
    /** The stored plan, as it is before any change. */
    val original: MealPlan? = null,
    val isLoadingPlan: Boolean = true,
    val loadError: AiError? = null,
    val isOptimizing: Boolean = false,
    val optimizeError: AiError? = null,
    /** The optimized draft for [goal]; nothing is stored until it is accepted. */
    val draft: MealPlan? = null,
    val changes: List<MealServingChange> = emptyList(),
    val isAccepting: Boolean = false,
    val acceptError: AiError? = null,
    /** Meals whose new servings are already saved, so a retry only saves the rest. */
    val appliedMealIds: Set<String> = emptySet(),
    /** Every change was saved: the plan now is the optimized one. */
    val isAccepted: Boolean = false,
) {
    /** The draft proposes nothing different: the plan is already as good as it gets for [goal]. */
    val isUnchanged: Boolean get() = draft != null && changes.isEmpty()

    /** Daily average of the plan before, when the server reported one. */
    val dailyAverageBefore: NutritionalInfo? get() = original?.nutritionalSummary?.dailyAverage

    /** Daily average with the draft, when the server reported one. */
    val dailyAverageAfter: NutritionalInfo? get() = draft?.nutritionalSummary?.dailyAverage
}

/**
 * Shared logic of the optimize-plan flow (AIA-605), used by the Compose and SwiftUI screens: pick a
 * goal, see what the AI Advisor would change, then accept or discard.
 *
 * - [start] loads the stored plan, the "before" of the comparison.
 * - [optimize] asks for a draft toward the goal. The server never changes the stored plan; a newer
 *   request makes an older one irrelevant, and changing the goal drops the draft.
 * - [accept] saves the draft by updating the servings of each changed meal. If one update fails the
 *   ones already saved are kept and a retry only saves the rest, so nothing is applied twice.
 * - Discarding is simply leaving: nothing was stored.
 *
 * The functions are `suspend` so the UI owns the coroutine scope; [CancellationException] is
 * rethrown so leaving the screen cancels cleanly.
 */
class OptimizePlanViewModel(
    private val advisor: AiAdvisor,
    private val plans: DietaryRepository,
) {

    private val _state = MutableStateFlow(OptimizePlanUiState())
    val state: StateFlow<OptimizePlanUiState> = _state.asStateFlow()

    private var planId: String? = null

    /** Identifies the latest optimization; answers to older ones are ignored. */
    private var generation = 0

    /** Load the plan [planId]; also the retry after a failed load. */
    suspend fun start(planId: String) {
        this.planId = planId
        if (_state.value.original != null) return
        _state.update { it.copy(isLoadingPlan = true, loadError = null) }
        try {
            val plan = plans.getMealPlan(planId)
            _state.update { it.copy(original = plan, isLoadingPlan = false) }
        } catch (e: CancellationException) {
            _state.update { it.copy(isLoadingPlan = false) }
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            _state.update { it.copy(isLoadingPlan = false, loadError = e.toAiError()) }
        }
    }

    /** Choose the goal; a draft made for another goal no longer applies. */
    fun onGoalChange(goal: String) {
        val current = _state.value
        if (goal !in AiAdvisor.GOALS || goal == current.goal || current.isAccepting || current.isAccepted) return
        generation++
        _state.update {
            it.copy(goal = goal, draft = null, changes = emptyList(), isOptimizing = false, optimizeError = null)
        }
    }

    /** Ask for a draft toward the chosen goal; also the retry after a failure. */
    suspend fun optimize() {
        val id = planId ?: return
        val current = _state.value
        val original = current.original ?: return
        if (current.isAccepting || current.isAccepted) return
        val token = ++generation
        _state.update { it.copy(isOptimizing = true, optimizeError = null, draft = null, changes = emptyList()) }
        try {
            val outcome = advisor.optimizePlan(id, current.goal)
            if (token != generation) return
            _state.update { state ->
                when (outcome) {
                    is AiResult.Success -> state.copy(
                        isOptimizing = false,
                        draft = outcome.value,
                        changes = servingChanges(original, outcome.value),
                        acceptError = null,
                        appliedMealIds = emptySet(),
                    )
                    is AiResult.Failure -> state.copy(isOptimizing = false, optimizeError = outcome.error)
                }
            }
        } catch (e: CancellationException) {
            if (token == generation) _state.update { it.copy(isOptimizing = false) }
            throw e
        }
    }

    /** Save the draft: the new servings of every changed meal. Also the retry after a failure. */
    suspend fun accept() {
        val id = planId ?: return
        val current = _state.value
        if (current.isAccepting || current.isAccepted || current.isOptimizing || current.changes.isEmpty()) return
        _state.update { it.copy(isAccepting = true, acceptError = null) }
        try {
            for (change in current.changes) {
                if (change.mealId in _state.value.appliedMealIds) continue
                plans.updateMeal(id, change.mealId, UpdateMealRequest(servings = change.after))
                _state.update { it.copy(appliedMealIds = it.appliedMealIds + change.mealId) }
            }
            _state.update { it.copy(isAccepting = false, isAccepted = true) }
        } catch (e: CancellationException) {
            _state.update { it.copy(isAccepting = false) }
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            _state.update { it.copy(isAccepting = false, acceptError = e.toAiError()) }
        }
    }

    private fun servingChanges(original: MealPlan, draft: MealPlan): List<MealServingChange> {
        val proposed = draft.meals.associateBy { it.id }
        return original.meals.mapNotNull { meal ->
            val after = proposed[meal.id]?.servings ?: return@mapNotNull null
            if (after == meal.servings) return@mapNotNull null
            MealServingChange(
                mealId = meal.id,
                mealType = meal.mealType,
                recipeName = meal.recipe?.name,
                date = meal.dayIndex?.let { IsoDate.addDays(original.startDate, it) },
                before = meal.servings,
                after = after,
            )
        }
    }
}
