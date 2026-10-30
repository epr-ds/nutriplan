@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.nutriplan.android.screen.home

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.clickable
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.res.stringResource
import com.nutriplan.android.R
import com.nutriplan.android.component.EmptyState
import com.nutriplan.android.component.ErrorState
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.android.di.koinInject
import com.nutriplan.android.i18n.messageRes
import com.nutriplan.android.i18n.planStatusLabelRes
import com.nutriplan.android.screen.plans.formatPlanDay
import com.nutriplan.shared.data.model.MealPlanSummary
import com.nutriplan.shared.planning.MealPlanListViewModel
import kotlinx.coroutines.launch

/**
 * Home screen displaying the user's meal plans.
 */
@Composable
fun HomeScreen(
    onNavigateToMealPlanDetail: (String) -> Unit,
    onNavigateToCreateMealPlan: () -> Unit,
    onNavigateToRecipeSearch: () -> Unit,
    onNavigateToAiRecommendations: () -> Unit,
    onNavigateToMealPlans: () -> Unit = {},
    onNavigateToAnalyzeMeal: () -> Unit = {},
    onNavigateToNotifications: () -> Unit = {},
    unreadCount: Int = 0,
) {
    // DPL-501: Home shows the same plans as the full list, from the shared view-model.
    val viewModel = koinInject<MealPlanListViewModel>()
    val state by viewModel.state.collectAsState()
    val scope = rememberCoroutineScope()

    LaunchedEffect(viewModel) { viewModel.load() }

    val isLoading = state.isLoading && state.plans.isEmpty()
    val mealPlans = state.plans
    val errorMessage = state.error
        ?.takeIf { mealPlans.isEmpty() }
        ?.let { stringResource(it.messageRes(hasSavedPlans = false)) }

    val retryAction: () -> Unit = { scope.launch { viewModel.load() } }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { 
                    Text(
                        "NutriPlan",
                        color = MaterialTheme.colorScheme.onPrimary
                    ) 
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primary
                ),
                actions = {
                    // NTF-506: the entry point to the in-app notification center, with an unread badge.
                    IconButton(onClick = onNavigateToNotifications) {
                        Box(
                            modifier = Modifier.size(40.dp),
                            contentAlignment = Alignment.TopEnd,
                        ) {
                            Icon(
                                imageVector = Icons.Default.Notifications,
                                contentDescription = stringResource(R.string.notification_center_title),
                                tint = MaterialTheme.colorScheme.onPrimary,
                                modifier = Modifier.size(28.dp),
                            )
                            if (unreadCount > 0) {
                                Box(
                                    modifier = Modifier
                                        .size(10.dp)
                                        .background(MaterialTheme.colorScheme.error, CircleShape),
                                )
                            }
                        }
                    }
                },
            )
        },
        floatingActionButton = {
            FloatingActionButton(
                onClick = onNavigateToCreateMealPlan,
                containerColor = MaterialTheme.colorScheme.primary
            ) {
                Icon(
                    Icons.Default.Add,
                    contentDescription = "Create Meal Plan",
                    tint = MaterialTheme.colorScheme.onPrimary
                )
            }
        }
    ) { paddingValues ->
        if (isLoading) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(paddingValues),
                contentAlignment = Alignment.Center
            ) {
                // F24: Add contextual accessibility label for loading spinner
                Box(modifier = Modifier.semantics { contentDescription = "Loading meal plans" }) {
                    CircularProgressIndicator()
                }
            }
        } else if (errorMessage != null) {
            ErrorState(
                message = errorMessage!!,
                onRetry = retryAction,
                modifier = Modifier
                    .fillMaxSize()
                    .padding(paddingValues)
            )
        } else if (mealPlans.isEmpty()) {
            EmptyState(
                title = "No Meal Plans",
                description = "Create your first meal plan to get started.",
                actionLabel = "Create Meal Plan",
                onAction = onNavigateToCreateMealPlan,
                modifier = Modifier.padding(paddingValues)
            )
        } else {
            LazyColumn(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(paddingValues),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                items(mealPlans, key = { it.id }) { plan ->
                    MealPlanCard(
                        mealPlan = plan,
                        onClick = { onNavigateToMealPlanDetail(plan.id) }
                    )
                }
                
                item {
                    Spacer(modifier = Modifier.height(16.dp))
                    
                    // Quick actions
                    Text(
                        text = stringResource(R.string.home_quick_actions),
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.onSurface
                    )

                    Spacer(modifier = Modifier.height(8.dp))

                    // Two per row, so the labels fit on a phone.
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        QuickActionCard(
                            icon = Icons.Default.CalendarMonth,
                            label = stringResource(R.string.meal_plans_all),
                            onClick = onNavigateToMealPlans,
                            modifier = Modifier.weight(1f)
                        )

                        QuickActionCard(
                            icon = Icons.Default.Search,
                            label = stringResource(R.string.home_action_recipes),
                            onClick = onNavigateToRecipeSearch,
                            modifier = Modifier.weight(1f)
                        )
                    }

                    Spacer(modifier = Modifier.height(8.dp))

                    Row(
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        QuickActionCard(
                            icon = Icons.Default.AutoAwesome,
                            label = stringResource(R.string.home_action_ai_recommendations),
                            onClick = onNavigateToAiRecommendations,
                            modifier = Modifier.weight(1f)
                        )

                        // AIA-607: describe a meal and get its nutrition and warnings.
                        QuickActionCard(
                            icon = Icons.Default.Restaurant,
                            label = stringResource(R.string.home_action_analyze_meal),
                            onClick = onNavigateToAnalyzeMeal,
                            modifier = Modifier.weight(1f)
                        )
                    }
                }
            }
        }
    }
}

/**
 * Meal plan card component.
 */
@Composable
fun MealPlanCard(
    mealPlan: MealPlanSummary,
    onClick: () -> Unit
) {
    val dates = stringResource(
        R.string.plan_detail_dates,
        formatPlanDay(mealPlan.startDate),
        formatPlanDay(mealPlan.endDate),
    )
    val status = planStatusLabelRes(mealPlan.status)?.let { stringResource(it) } ?: mealPlan.status
    Card(
        modifier = Modifier
            .fillMaxWidth()
            // F11: Add accessible name for screen readers (WCAG 4.1.2)
            .semantics { contentDescription = "${mealPlan.name}, $dates, $status" }
            .clickable(onClick = onClick),
        shape = MaterialTheme.shapes.medium
    ) {
        Column(
            modifier = Modifier.padding(16.dp)
        ) {
            Text(
                text = mealPlan.name,
                style = MaterialTheme.typography.titleLarge,
                color = MaterialTheme.colorScheme.onSurface
            )
            
            Spacer(modifier = Modifier.height(8.dp))
            
            Text(
                text = dates,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurface
            )

            Spacer(modifier = Modifier.height(8.dp))

            Text(
                text = status,
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.primary
            )
        }
    }
}

/**
 * Quick action card component.
 */
@Composable
fun QuickActionCard(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    label: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier
            // F12: Add accessible name for screen readers (WCAG 4.1.2)
            // F19: Use defaultMinSize instead of fixed height to prevent text clipping at large dynamic type (WCAG 1.4.4)
            .semantics { contentDescription = label }
            .defaultMinSize(minHeight = 80.dp)
            .clickable(onClick = onClick),
        shape = MaterialTheme.shapes.medium
    ) {
        Row(
            modifier = Modifier
                .fillMaxSize()
                .padding(12.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                icon,
                contentDescription = label,
                tint = MaterialTheme.colorScheme.primary,
                modifier = Modifier.size(24.dp)
            )
            
            Text(
                text = label,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurface
            )
        }
    }
}
