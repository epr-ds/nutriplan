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
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
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
import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.model.PlanMeal
import com.nutriplan.shared.planning.MealPlanDay
import com.nutriplan.shared.planning.MealPlanDetailError
import com.nutriplan.shared.planning.MealPlanDetailUiState
import com.nutriplan.shared.planning.MealPlanDetailViewModel
import com.nutriplan.shared.planning.MealSection
import kotlinx.coroutines.launch

/** Test tags for the plan detail screen (used by the Robolectric UI tests). */
object MealPlanDetailTestTags {
    const val LIST = "plan_detail_list"
    const val LOADING = "plan_detail_loading"
    const val ADD_MEAL = "plan_detail_add_meal"
    const val EDIT = "plan_detail_edit"
    const val ERROR_BANNER = "plan_detail_error_banner"
    const val MEAL_CARD = "plan_detail_meal_card"
}

/**
 * DPL-505: one meal plan, day by day, with its meals grouped by meal type.
 *
 * Backed by the shared [MealPlanDetailViewModel]. [onAddMeal] and [onEditPlan] are the entry points
 * to add or change meals; [onSessionExpired] is called when the server rejects the session so the
 * app can send the user back to sign-in.
 */
@Composable
fun MealPlanDetailScreen(
    planId: String,
    onBack: () -> Unit,
    onAddMeal: () -> Unit,
    onEditPlan: () -> Unit,
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
        onEditPlan = onEditPlan,
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
    onEditPlan: () -> Unit,
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
                actions = {
                    if (plan != null) {
                        IconButton(onClick = onEditPlan, modifier = Modifier.testTag(MealPlanDetailTestTags.EDIT)) {
                            Icon(
                                Icons.Default.Edit,
                                contentDescription = stringResource(R.string.cd_plan_detail_edit),
                            )
                        }
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

        item(key = "summary") { PlanSummary(plan) }

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
                item(key = "day-${day.date}") { DayHeader(day) }
                day.sections.forEach { section ->
                    item(key = "section-${day.date}-${section.mealType}") { SectionLabel(section) }
                    items(section.meals.size, key = { section.meals[it].id }) { index ->
                        MealCard(section.meals[index])
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
        plan.targetCalories?.let { target ->
            Text(
                text = stringResource(R.string.plan_detail_target_calories, target),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun DayHeader(day: MealPlanDay) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = 8.dp)
            .semantics(mergeDescendants = true) { heading() },
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(
            text = formatPlanDay(day.date),
            style = MaterialTheme.typography.titleMedium,
        )
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

@Composable
private fun MealCard(meal: PlanMeal) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .testTag(MealPlanDetailTestTags.MEAL_CARD)
            .semantics(mergeDescendants = true) {},
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(text = meal.recipeName, style = MaterialTheme.typography.titleSmall)
            val details = listOfNotNull(
                meal.calories?.let { stringResource(R.string.plan_detail_meal_calories, it) },
                meal.portionSize?.let { stringResource(R.string.plan_detail_meal_portion, formatPortion(it)) },
            )
            if (details.isNotEmpty()) {
                Text(
                    text = details.joinToString(" · "),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

/** "2" for 2.0 and "1.5" for 1.5, so whole portions have no trailing ".0". */
private fun formatPortion(portion: Double): String =
    if (portion % 1.0 == 0.0) portion.toInt().toString() else portion.toString()
