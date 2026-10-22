@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.nutriplan.android.screen.plans

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
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
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.nutriplan.android.R
import com.nutriplan.android.component.EmptyState
import com.nutriplan.android.component.ErrorState
import com.nutriplan.android.di.koinInject
import com.nutriplan.android.i18n.mealTypeLabelRes
import com.nutriplan.android.i18n.messageRes
import com.nutriplan.shared.data.local.ChangeKind
import com.nutriplan.shared.data.local.PendingChange
import com.nutriplan.shared.data.local.PendingMeal
import com.nutriplan.shared.data.local.isPending
import com.nutriplan.shared.data.local.isWaitingToSync
import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.model.PlanMeal
import com.nutriplan.shared.planning.MealPlanDay
import com.nutriplan.shared.planning.MealPlanDetailError
import com.nutriplan.shared.planning.MealPlanDetailUiState
import com.nutriplan.shared.planning.MealPlanDetailViewModel
import com.nutriplan.shared.planning.MealSection
import com.nutriplan.shared.planning.toNutritionSummaryUi
import kotlinx.coroutines.launch

/** Test tags for the plan detail screen (used by the Robolectric UI tests). */
object MealPlanDetailTestTags {
    const val LIST = "plan_detail_list"
    const val LOADING = "plan_detail_loading"
    const val ADD_MEAL = "plan_detail_add_meal"
    const val ERROR_BANNER = "plan_detail_error_banner"
    const val MEAL_CARD = "plan_detail_meal_card"
    const val PENDING_LABEL = "plan_detail_pending_label"
    const val FAILED_ADD = "plan_detail_failed_add"
    const val FAILED_CHANGE = "plan_detail_failed_change"
}

/**
 * DPL-505: one meal plan, day by day, with its meals grouped by meal type.
 *
 * Backed by the shared [MealPlanDetailViewModel]. [onAddMeal] is the entry point to add a meal;
 * [onSessionExpired] is called when the server rejects the session so the app can send the user
 * back to sign-in. (The API has no endpoint to rename a plan or change its dates, so there is no
 * edit action.)
 */
@Composable
fun MealPlanDetailScreen(
    planId: String,
    onBack: () -> Unit,
    onAddMeal: () -> Unit,
    onEditMeal: (mealId: String) -> Unit,
    onSessionExpired: () -> Unit,
) {
    val viewModel = koinInject<MealPlanDetailViewModel>()
    val state by viewModel.state.collectAsState()
    val scope = rememberCoroutineScope()

    LaunchedEffect(viewModel, planId) { viewModel.load(planId) }
    LaunchedEffect(state.error) {
        if (state.error == MealPlanDetailError.SESSION_EXPIRED) onSessionExpired()
    }

    MealPlanDetailScreenContent(
        state = state,
        onRefresh = { scope.launch { viewModel.refresh() } },
        onRetry = { scope.launch { viewModel.load(planId) } },
        onBack = onBack,
        onAddMeal = onAddMeal,
        onEditMeal = onEditMeal,
        onDismissFailedAdd = viewModel::dismissFailedAdd,
        onDismissFailedChange = viewModel::dismissFailedChange,
    )
}

/** Stateless plan detail: renders [state]; every action is a callback. */
@Composable
fun MealPlanDetailScreenContent(
    state: MealPlanDetailUiState,
    onRefresh: () -> Unit,
    onRetry: () -> Unit,
    onBack: () -> Unit,
    onAddMeal: () -> Unit,
    onEditMeal: (mealId: String) -> Unit = {},
    onDismissFailedAdd: (id: Long) -> Unit = {},
    onDismissFailedChange: (id: Long) -> Unit = {},
) {
    val plan = state.plan
    val error = state.error
    val loadingDescription = stringResource(R.string.cd_plan_detail_loading)

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = plan?.name ?: stringResource(R.string.plan_detail_title_fallback),
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
            state.isLoading && plan == null -> Box(
                modifier = content.testTag(MealPlanDetailTestTags.LOADING),
                contentAlignment = Alignment.Center,
            ) {
                CircularProgressIndicator(
                    modifier = Modifier.semantics { contentDescription = loadingDescription },
                )
            }

            error != null && plan == null -> ErrorState(
                message = stringResource(error.messageRes(hasSavedPlan = false)),
                // A plan that no longer exists cannot be retried: the action goes back instead.
                onRetry = if (error == MealPlanDetailError.NOT_FOUND) onBack else onRetry,
                modifier = content,
                actionLabel = stringResource(
                    if (error == MealPlanDetailError.NOT_FOUND) {
                        R.string.plan_detail_back_to_plans
                    } else {
                        R.string.meal_plans_retry
                    },
                ),
            )

            plan != null -> PullToRefreshBox(
                isRefreshing = state.isRefreshing,
                onRefresh = onRefresh,
                modifier = content,
            ) {
                PlanDetailList(
                    plan = plan,
                    days = state.days,
                    error = error,
                    hasNoMeals = state.hasNoMeals,
                    onAddMeal = onAddMeal,
                    onEditMeal = onEditMeal,
                    failedAdds = state.failedAdds,
                    onDismissFailedAdd = onDismissFailedAdd,
                    failedChanges = state.failedChanges,
                    onDismissFailedChange = onDismissFailedChange,
                )
            }
        }
    }
}

@Composable
private fun PlanDetailList(
    plan: MealPlan,
    days: List<MealPlanDay>,
    error: MealPlanDetailError?,
    hasNoMeals: Boolean,
    onAddMeal: () -> Unit,
    onEditMeal: (mealId: String) -> Unit,
    failedAdds: List<PendingMeal>,
    onDismissFailedAdd: (id: Long) -> Unit,
    failedChanges: List<PendingChange>,
    onDismissFailedChange: (id: Long) -> Unit,
) {
    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .testTag(MealPlanDetailTestTags.LIST),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        if (error != null) {
            item(key = "error") {
                Text(
                    text = stringResource(error.messageRes(hasSavedPlan = true)),
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier
                        .testTag(MealPlanDetailTestTags.ERROR_BANNER)
                        .semantics { liveRegion = LiveRegionMode.Polite },
                )
            }
        }

        items(failedAdds, key = { "failed-${it.id}" }) { failed ->
            FailedAddNotice(failed, onDismiss = { onDismissFailedAdd(failed.id) })
        }

        items(failedChanges, key = { "failed-change-${it.id}" }) { failed ->
            FailedChangeNotice(failed, onDismiss = { onDismissFailedChange(failed.id) })
        }

        item(key = "summary") { PlanSummary(plan) }

        item(key = "nutrition") { NutritionSummaryCard(plan.nutritionalSummary.toNutritionSummaryUi()) }

        if (hasNoMeals) {
            item(key = "empty") {
                EmptyState(
                    title = stringResource(R.string.plan_detail_empty_title),
                    description = stringResource(R.string.plan_detail_empty_description),
                    actionLabel = stringResource(R.string.plan_detail_add_meal),
                    onAction = onAddMeal,
                )
            }
        } else {
            days.forEach { day ->
                val dayKey = day.dayIndex?.toString() ?: "unassigned"
                item(key = "day-$dayKey") { DayHeader(day) }
                day.sections.forEach { section ->
                    item(key = "section-$dayKey-${section.mealType}") { SectionLabel(section) }
                    items(section.meals.size, key = { section.meals[it].id }) { index ->
                        MealCard(section.meals[index], onClick = { onEditMeal(section.meals[index].id) })
                    }
                }
            }
            item(key = "add") {
                Button(
                    onClick = onAddMeal,
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag(MealPlanDetailTestTags.ADD_MEAL),
                ) {
                    Icon(Icons.Default.Add, contentDescription = null)
                    Text(
                        text = stringResource(R.string.plan_detail_add_meal),
                        modifier = Modifier.padding(start = 8.dp),
                    )
                }
            }
        }
    }
}

@Composable
private fun PlanSummary(plan: MealPlan) {

    Column(modifier = Modifier.semantics(mergeDescendants = true) {}) {
        Text(
            text = stringResource(
                R.string.plan_detail_dates,
                formatPlanDay(plan.startDate),
                formatPlanDay(plan.endDate),
            ),
            style = MaterialTheme.typography.bodyLarge,
        )
        Text(
            text = stringResource(R.string.plan_detail_target_calories, plan.dailyCalorieTarget),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun DayHeader(day: MealPlanDay) {
    val title = when {
        day.dayIndex == null -> stringResource(R.string.plan_detail_day_unassigned)
        day.date != null -> "${stringResource(R.string.plan_detail_day_title, day.dayIndex!! + 1)} · ${formatPlanDay(day.date!!)}"
        else -> stringResource(R.string.plan_detail_day_title, day.dayIndex!! + 1)
    }
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = 8.dp)
            .semantics(mergeDescendants = true) { heading() },
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(text = title, style = MaterialTheme.typography.titleMedium)
        day.totalCalories?.let { total ->
            Text(
                text = stringResource(R.string.plan_detail_day_calories, total),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun SectionLabel(section: MealSection) {
    Text(
        text = mealTypeLabelRes(section.mealType)?.let { stringResource(it) } ?: section.mealType,
        style = MaterialTheme.typography.labelLarge,
        color = MaterialTheme.colorScheme.primary,
    )
}

/**
 * A meal that was added while offline and then refused by the server (DPL-407): it is no longer in
 * the plan, so the user is told which one and why, and can dismiss the message.
 */
@Composable
private fun FailedAddNotice(failed: PendingMeal, onDismiss: () -> Unit) {
    val name = failed.recipe.name.ifBlank { failed.recipeId }
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .testTag(MealPlanDetailTestTags.FAILED_ADD)
            .semantics { liveRegion = LiveRegionMode.Polite },
    ) {
        Text(
            text = stringResource(R.string.pending_meal_failed_title, name),
            style = MaterialTheme.typography.titleSmall,
            color = MaterialTheme.colorScheme.error,
        )
        failed.failure?.let {
            Text(
                text = stringResource(it.messageRes()),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.error,
            )
        }
        val dismissLabel = stringResource(R.string.cd_pending_meal_dismiss, name)
        TextButton(
            onClick = onDismiss,
            modifier = Modifier.semantics { contentDescription = dismissLabel },
        ) {
            Text(stringResource(R.string.pending_meal_dismiss))
        }
    }
}

/**
 * An edit or removal made while offline that the server then refused (DPL-407): the plan shows the
 * server's version again, so the user is told which meal and why, and can dismiss the message.
 */
@Composable
private fun FailedChangeNotice(failed: PendingChange, onDismiss: () -> Unit) {
    val mealType = mealTypeLabelRes(failed.mealType)?.let { stringResource(it) } ?: failed.mealType
    val title = stringResource(
        if (failed.kind == ChangeKind.REMOVE) R.string.pending_change_remove_failed_title else R.string.pending_change_failed_title,
        mealType,
    )
    val dismissLabel = stringResource(R.string.cd_pending_change_dismiss, mealType)
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .testTag(MealPlanDetailTestTags.FAILED_CHANGE)
            .semantics { liveRegion = LiveRegionMode.Polite },
    ) {
        Text(text = title, style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.error)
        failed.failure?.let {
            Text(text = stringResource(it.messageRes()), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.error)
        }
        TextButton(onClick = onDismiss, modifier = Modifier.semantics { contentDescription = dismissLabel }) {
            Text(stringResource(R.string.pending_meal_dismiss))
        }
    }
}

@Composable
private fun MealCard(meal: PlanMeal, onClick: () -> Unit) {
    Card(
        onClick = onClick,
        // A meal that has not reached the server yet has nothing to edit.
        enabled = !meal.isPending,
        modifier = Modifier
            .fillMaxWidth()
            .testTag(MealPlanDetailTestTags.MEAL_CARD)
            .semantics(mergeDescendants = true) {},
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            // Plan reads do not include the recipe, so only a freshly added meal has a name.
            Text(
                text = meal.recipe?.name ?: stringResource(R.string.plan_detail_meal_unnamed),
                style = MaterialTheme.typography.titleSmall,
            )
            if (meal.isWaitingToSync) {
                Text(
                    text = stringResource(R.string.plan_detail_meal_pending),
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.tertiary,
                    modifier = Modifier.testTag(MealPlanDetailTestTags.PENDING_LABEL),
                )
            }
            val servings = stringResource(R.string.plan_detail_meal_servings, formatQuantity(meal.servings))
            val calories = meal.nutritionalInfo?.calories?.let { stringResource(R.string.plan_detail_meal_calories, it) }
            Text(
                text = listOfNotNull(servings, calories).joinToString(" · "),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            val info = meal.nutritionalInfo
            val macros = listOfNotNull(
                info?.protein?.let { stringResource(R.string.plan_detail_meal_protein, formatQuantity(it)) },
                info?.carbs?.let { stringResource(R.string.plan_detail_meal_carbs, formatQuantity(it)) },
                info?.fat?.let { stringResource(R.string.plan_detail_meal_fat, formatQuantity(it)) },
            )
            meal.satisfactionLevel?.let {
                Text(
                    text = stringResource(R.string.plan_detail_meal_rated, it),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            if (macros.isNotEmpty()) {
                Text(
                    text = macros.joinToString(" · "),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

/** "2" for 2.0 and "1.5" for 1.5, so whole quantities have no trailing ".0". */
private fun formatQuantity(value: Double): String =
    if (value % 1.0 == 0.0) value.toInt().toString() else value.toString()
