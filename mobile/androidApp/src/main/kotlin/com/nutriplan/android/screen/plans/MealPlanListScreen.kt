@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.nutriplan.android.screen.plans

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FloatingActionButton
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
import com.nutriplan.android.i18n.messageRes
import com.nutriplan.android.screen.home.MealPlanCard
import com.nutriplan.shared.planning.MealPlanListError
import com.nutriplan.shared.planning.MealPlanListUiState
import com.nutriplan.shared.planning.MealPlanListViewModel
import com.nutriplan.shared.planning.plansOpenForMeals
import kotlinx.coroutines.launch

/** Test tags for the meal plan list (used by the Robolectric UI tests). */
object MealPlanListTestTags {
    const val LIST = "meal_plan_list"
    const val LOADING = "meal_plan_loading"
    const val CREATE = "meal_plan_create"
    const val ERROR_BANNER = "meal_plan_error_banner"
}

/**
 * DPL-501: the user's meal plans, newest first, with pull-to-refresh and a button to create one.
 *
 * Backed by the shared [MealPlanListViewModel]; plans come from the on-device cache when the server
 * cannot be reached. [onSessionExpired] is called when the server rejects the session so the app
 * can send the user back to sign-in.
 *
 * With [isPicking] (AIA-604) it is the step that chooses the plan to add a recipe to: only plans that
 * still take meals are listed, and there is no button to create one.
 */
@Composable
fun MealPlanListScreen(
    onPlanClick: (String) -> Unit,
    onCreatePlan: () -> Unit,
    onBack: () -> Unit,
    onSessionExpired: () -> Unit,
    isPicking: Boolean = false,
) {
    val viewModel = koinInject<MealPlanListViewModel>()
    val state by viewModel.state.collectAsState()
    val scope = rememberCoroutineScope()

    LaunchedEffect(viewModel) { viewModel.load() }
    LaunchedEffect(state.error) {
        if (state.error == MealPlanListError.SESSION_EXPIRED) onSessionExpired()
    }

    MealPlanListScreenContent(
        state = state,
        onRefresh = { scope.launch { viewModel.refresh() } },
        onRetry = { scope.launch { viewModel.load() } },
        onPlanClick = onPlanClick,
        onCreatePlan = onCreatePlan,
        onBack = onBack,
        isPicking = isPicking,
    )
}

/** Stateless meal plan list: renders [state]; every action is a callback. */
@Composable
fun MealPlanListScreenContent(
    state: MealPlanListUiState,
    onRefresh: () -> Unit,
    onRetry: () -> Unit,
    onPlanClick: (String) -> Unit,
    onCreatePlan: () -> Unit,
    onBack: (() -> Unit)? = null,
    isPicking: Boolean = false,
) {
    val error = state.error
    val plans = if (isPicking) state.plansOpenForMeals else state.plans
    val loadingDescription = stringResource(R.string.cd_meal_plans_loading)

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = stringResource(if (isPicking) R.string.pick_plan_title else R.string.meal_plans_title),
                        modifier = Modifier.semantics { heading() },
                    )
                },
                navigationIcon = {
                    if (onBack != null) {
                        IconButton(onClick = onBack) {
                            Icon(
                                Icons.AutoMirrored.Filled.ArrowBack,
                                contentDescription = stringResource(R.string.cd_meal_plans_back),
                            )
                        }
                    }
                },
            )
        },
        floatingActionButton = {
            if (!isPicking) FloatingActionButton(
                onClick = onCreatePlan,
                modifier = Modifier.testTag(MealPlanListTestTags.CREATE),
            ) {
                Icon(Icons.Default.Add, contentDescription = stringResource(R.string.cd_meal_plans_create))
            }
        },
    ) { paddingValues ->
        val content = Modifier
            .fillMaxSize()
            .padding(paddingValues)

        when {
            state.isLoading && plans.isEmpty() -> Box(
                modifier = content.testTag(MealPlanListTestTags.LOADING),
                contentAlignment = Alignment.Center,
            ) {
                CircularProgressIndicator(
                    modifier = Modifier.semantics { contentDescription = loadingDescription },
                )
            }

            error != null && plans.isEmpty() -> ErrorState(
                message = stringResource(error.messageRes(hasSavedPlans = false)),
                onRetry = onRetry,
                modifier = content,
                actionLabel = stringResource(R.string.meal_plans_retry),
            )

            !state.isLoading && error == null && plans.isEmpty() -> if (isPicking) {
                EmptyState(
                    title = stringResource(R.string.pick_plan_empty_title),
                    description = stringResource(R.string.pick_plan_empty_description),
                    modifier = content,
                )
            } else {
                EmptyState(
                    title = stringResource(R.string.meal_plans_empty_title),
                    description = stringResource(R.string.meal_plans_empty_description),
                    modifier = content,
                    actionLabel = stringResource(R.string.meal_plans_empty_action),
                    onAction = onCreatePlan,
                )
            }

            else -> PullToRefreshBox(
                isRefreshing = state.isRefreshing,
                onRefresh = onRefresh,
                modifier = content,
            ) {
                LazyColumn(
                    modifier = Modifier
                        .fillMaxSize()
                        .testTag(MealPlanListTestTags.LIST),
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(16.dp),
                ) {
                    if (error != null) {
                        item(key = "error") {
                            Text(
                                text = stringResource(error.messageRes(hasSavedPlans = true)),
                                color = MaterialTheme.colorScheme.error,
                                style = MaterialTheme.typography.bodyMedium,
                                modifier = Modifier
                                    .testTag(MealPlanListTestTags.ERROR_BANNER)
                                    .semantics { liveRegion = LiveRegionMode.Polite },
                            )
                        }
                    }
                    items(plans, key = { it.id }) { plan ->
                        MealPlanCard(mealPlan = plan, onClick = { onPlanClick(plan.id) })
                    }
                }
            }
        }
    }
}
