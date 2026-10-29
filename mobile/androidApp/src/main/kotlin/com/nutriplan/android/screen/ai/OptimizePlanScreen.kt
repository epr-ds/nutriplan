@file:OptIn(
    androidx.compose.material3.ExperimentalMaterial3Api::class,
    androidx.compose.foundation.layout.ExperimentalLayoutApi::class,
)

package com.nutriplan.android.screen.ai

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.nutriplan.android.R
import com.nutriplan.android.component.EmptyState
import com.nutriplan.android.component.ErrorState
import com.nutriplan.android.di.koinInject
import com.nutriplan.android.i18n.acceptMessageRes
import com.nutriplan.android.i18n.mealTypeLabelRes
import com.nutriplan.android.i18n.optimizeMessageRes
import com.nutriplan.android.screen.plans.formatPlanDay
import com.nutriplan.android.screen.recipes.formatQuantity
import com.nutriplan.shared.ai.AiAdvisor
import com.nutriplan.shared.ai.AiError
import com.nutriplan.shared.ai.AiLoadingStage
import com.nutriplan.shared.ai.MealServingChange
import com.nutriplan.shared.ai.OptimizePlanUiState
import com.nutriplan.shared.ai.OptimizePlanViewModel
import com.nutriplan.shared.data.model.NutritionalInfo
import kotlinx.coroutines.launch
import kotlin.math.roundToInt

/** Test tags for the optimize-plan screen (used by the Robolectric UI tests). */
object OptimizePlanTestTags {
    const val LIST = "optimize_list"
    const val PLAN_LOADING = "optimize_plan_loading"
    const val GOAL_CHIP = "optimize_goal_chip"
    const val SUBMIT = "optimize_submit"
    const val LOADING = "optimize_loading"
    const val ERROR_BANNER = "optimize_error_banner"
    const val UNCHANGED = "optimize_unchanged"
    const val DAILY = "optimize_daily"
    const val CHANGE = "optimize_change"
    const val ACCEPT = "optimize_accept"
    const val DISCARD = "optimize_discard"
    const val ACCEPT_ERROR = "optimize_accept_error"
    const val DISCLAIMER = "optimize_disclaimer"
}

/**
 * AIA-605: optimize the plan [planId] with the AI Advisor. The user picks a goal, sees which meals
 * would change and how the daily average moves, then accepts (the new servings are saved) or
 * discards (nothing was stored). [onDone] is called once the changes are saved; [onSessionExpired]
 * when the server rejects the session.
 */
@Composable
fun OptimizePlanScreen(
    planId: String,
    onBack: () -> Unit,
    onDone: () -> Unit,
    onSessionExpired: () -> Unit,
) {
    val viewModel = koinInject<OptimizePlanViewModel>()
    val state by viewModel.state.collectAsState()
    val scope = rememberCoroutineScope()

    LaunchedEffect(viewModel, planId) { viewModel.start(planId) }
    LaunchedEffect(state.isAccepted) { if (state.isAccepted) onDone() }
    LaunchedEffect(state.loadError, state.optimizeError, state.acceptError) {
        if (AiError.SESSION_EXPIRED in listOf(state.loadError, state.optimizeError, state.acceptError)) {
            onSessionExpired()
        }
    }

    OptimizePlanScreenContent(
        state = state,
        onGoalChange = viewModel::onGoalChange,
        onOptimize = { scope.launch { viewModel.optimize() } },
        onAccept = { scope.launch { viewModel.accept() } },
        onRetryLoad = { scope.launch { viewModel.start(planId) } },
        onBack = onBack,
        loadingStage = rememberAiLoadingStage(state.isOptimizing),
    )
}

/** Stateless optimize-plan flow: renders [state]; every action is a callback. Discard is [onBack]. */
@Composable
fun OptimizePlanScreenContent(
    state: OptimizePlanUiState,
    onGoalChange: (String) -> Unit,
    onOptimize: () -> Unit,
    onAccept: () -> Unit,
    onRetryLoad: () -> Unit,
    onBack: () -> Unit,
    /** How long the optimization has been running (AIA-606). */
    loadingStage: AiLoadingStage = AiLoadingStage.STARTED,
) {
    val planLoadingDescription = stringResource(R.string.cd_optimize_plan_loading)
    val loadingDescription = stringResource(R.string.cd_optimize_loading)
    val loadError = state.loadError

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = stringResource(R.string.optimize_title),
                        modifier = Modifier.semantics { heading() },
                    )
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(
                            Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = stringResource(R.string.cd_meal_plans_back),
                        )
                    }
                },
            )
        },
    ) { paddingValues ->
        val content = Modifier
            .fillMaxSize()
            .padding(paddingValues)

        when {
            state.original == null && loadError == null -> Box(
                modifier = content.testTag(OptimizePlanTestTags.PLAN_LOADING),
                contentAlignment = Alignment.Center,
            ) {
                CircularProgressIndicator(
                    modifier = Modifier.semantics { contentDescription = planLoadingDescription },
                )
            }

            state.original == null && loadError != null -> ErrorState(
                message = stringResource(loadError.optimizeMessageRes()),
                onRetry = onRetryLoad,
                modifier = content,
                actionLabel = stringResource(R.string.meal_plans_retry),
            )

            else -> LazyColumn(
                modifier = content.testTag(OptimizePlanTestTags.LIST),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                item(key = "goal") { GoalPicker(state, onGoalChange, onOptimize) }

                state.optimizeError?.let { error ->
                    item(key = "error") {
                        AiErrorCard(
                            message = stringResource(error.optimizeMessageRes()),
                            onRetry = onOptimize,
                            messageTestTag = OptimizePlanTestTags.ERROR_BANNER,
                            retryEnabled = !state.isOptimizing,
                        )
                    }
                }

                if (state.isOptimizing) {
                    item(key = "loading") {
                        AiLoadingSkeleton(
                            stage = loadingStage,
                            description = loadingDescription,
                            modifier = Modifier.testTag(OptimizePlanTestTags.LOADING),
                            cards = 2,
                        )
                    }
                } else if (state.isUnchanged) {
                    item(key = "unchanged") {
                        EmptyState(
                            title = stringResource(R.string.optimize_unchanged_title),
                            description = stringResource(R.string.optimize_unchanged_description),
                            modifier = Modifier.testTag(OptimizePlanTestTags.UNCHANGED),
                        )
                    }
                } else if (state.draft != null) {
                    proposal(state, onAccept, onBack)
                }
            }
        }
    }
}

private fun LazyListScope.proposal(
    state: OptimizePlanUiState,
    onAccept: () -> Unit,
    onDiscard: () -> Unit,
) {
    val before = state.dailyAverageBefore
    val after = state.dailyAverageAfter
    if (before != null && after != null) {
        item(key = "daily") { DailyAverageCard(before, after) }
    }
    item(key = "changes-heading") {
        Text(
            text = stringResource(R.string.optimize_changes_heading),
            style = MaterialTheme.typography.titleMedium,
            modifier = Modifier.semantics { heading() },
        )
    }
    items(state.changes, key = { it.mealId }) { change -> ChangeRow(change) }
    state.acceptError?.let { error ->
        item(key = "accept-error") {
            Text(
                text = stringResource(error.acceptMessageRes()),
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier
                    .testTag(OptimizePlanTestTags.ACCEPT_ERROR)
                    .semantics { liveRegion = LiveRegionMode.Polite },
            )
        }
    }
    item(key = "actions") {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(
                onClick = onAccept,
                enabled = !state.isAccepting,
                modifier = Modifier
                    .fillMaxWidth()
                    .testTag(OptimizePlanTestTags.ACCEPT),
            ) {
                Text(stringResource(R.string.optimize_accept))
            }
            OutlinedButton(
                onClick = onDiscard,
                enabled = !state.isAccepting,
                modifier = Modifier
                    .fillMaxWidth()
                    .testTag(OptimizePlanTestTags.DISCARD),
            ) {
                Text(stringResource(R.string.optimize_discard))
            }
        }
    }
    item(key = "disclaimer") {
        Card(
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
            modifier = Modifier
                .fillMaxWidth()
                .testTag(OptimizePlanTestTags.DISCLAIMER),
        ) {
            Text(
                text = stringResource(R.string.optimize_disclaimer),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(12.dp),
            )
        }
    }
}

@Composable
private fun GoalPicker(state: OptimizePlanUiState, onGoalChange: (String) -> Unit, onOptimize: () -> Unit) {
    val locked = state.isAccepting || state.isAccepted
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(
            text = stringResource(R.string.optimize_intro),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(text = stringResource(R.string.optimize_goal_label), style = MaterialTheme.typography.labelLarge)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            AiAdvisor.GOALS.forEach { goal ->
                val selected = state.goal == goal
                FilterChip(
                    selected = selected,
                    onClick = { onGoalChange(goal) },
                    enabled = !locked,
                    label = { Text(goalLabel(goal)) },
                    modifier = Modifier
                        .testTag(OptimizePlanTestTags.GOAL_CHIP)
                        .semantics { this.selected = selected },
                )
            }
        }
        Button(
            onClick = onOptimize,
            enabled = !state.isOptimizing && !locked,
            modifier = Modifier
                .fillMaxWidth()
                .testTag(OptimizePlanTestTags.SUBMIT),
        ) {
            Text(stringResource(R.string.optimize_submit))
        }
    }
}

@Composable
private fun goalLabel(goal: String): String = when (goal) {
    "balance_macros" -> stringResource(R.string.optimize_goal_balance_macros)
    "increase_protein" -> stringResource(R.string.optimize_goal_increase_protein)
    "reduce_calories" -> stringResource(R.string.optimize_goal_reduce_calories)
    "increase_satisfaction" -> stringResource(R.string.optimize_goal_increase_satisfaction)
    else -> goal
}

@Composable
private fun DailyAverageCard(before: NutritionalInfo, after: NutritionalInfo) {
    val beforeAfter = stringResource(
        R.string.cd_optimize_before_after,
        stringResource(R.string.optimize_daily_calories),
        before.calories.toString(),
        after.calories.toString(),
        stringResource(R.string.optimize_unit_kcal),
    )
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .testTag(OptimizePlanTestTags.DAILY)
            .semantics { contentDescription = beforeAfter },
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(
                text = stringResource(R.string.optimize_daily_heading),
                style = MaterialTheme.typography.titleSmall,
            )
            val caloriesBefore = before.calories
            val caloriesAfter = after.calories
            if (caloriesBefore != null && caloriesAfter != null) {
                BeforeAfterLine(
                    label = stringResource(R.string.optimize_daily_calories),
                    before = caloriesBefore.toString(),
                    after = caloriesAfter.toString(),
                    unit = stringResource(R.string.optimize_unit_kcal),
                )
            }
            val proteinBefore = before.protein
            val proteinAfter = after.protein
            if (proteinBefore != null && proteinAfter != null) {
                BeforeAfterLine(
                    label = stringResource(R.string.optimize_daily_protein),
                    before = proteinBefore.roundToInt().toString(),
                    after = proteinAfter.roundToInt().toString(),
                    unit = stringResource(R.string.optimize_unit_grams),
                )
            }
        }
    }
}

@Composable
private fun BeforeAfterLine(label: String, before: String, after: String, unit: String) {
    val description = stringResource(R.string.cd_optimize_before_after, label, before, after, unit)
    Row(
        horizontalArrangement = Arrangement.SpaceBetween,
        modifier = Modifier
            .fillMaxWidth()
            .clearAndSetSemantics { contentDescription = description },
    ) {
        Text(text = label, style = MaterialTheme.typography.bodyMedium)
        Text(
            text = stringResource(R.string.optimize_before_after, before, after, unit),
            style = MaterialTheme.typography.bodyMedium,
        )
    }
}

@Composable
private fun ChangeRow(change: MealServingChange) {
    val mealType = mealTypeLabelRes(change.mealType)?.let { stringResource(it) } ?: change.mealType
    val name = change.recipeName ?: stringResource(R.string.plan_detail_meal_unnamed)
    val where = listOfNotNull(mealType, change.date?.let { formatPlanDay(it) }).joinToString(" · ")
    val before = formatQuantity(change.before)
    val after = formatQuantity(change.after)
    val description = stringResource(R.string.cd_optimize_change, name, where, before, after)
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .testTag(OptimizePlanTestTags.CHANGE)
            .clearAndSetSemantics { contentDescription = description },
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(text = name, style = MaterialTheme.typography.titleSmall)
                Text(
                    text = where,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Text(
                text = stringResource(R.string.optimize_change_servings, before, after),
                style = MaterialTheme.typography.titleSmall,
            )
        }
    }
}
