@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.nutriplan.android.screen.home

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.clickable
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.nutriplan.android.component.EmptyState
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.android.di.koinInject

/**
 * Home screen displaying the user's meal plans.
 */
@Composable
fun HomeScreen(
    onNavigateToMealPlanDetail: (String) -> Unit,
    onNavigateToCreateMealPlan: () -> Unit,
    onNavigateToRecipeSearch: () -> Unit,
    onNavigateToAiRecommendations: () -> Unit
) {
    val dietaryRepository = koinInject<com.nutriplan.shared.data.repository.DietaryRepository>()
    
    var isLoading by remember { mutableStateOf(true) }
    var mealPlans by remember { mutableStateOf<List<com.nutriplan.shared.data.model.MealPlan>>(emptyList()) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        // TODO: Load meal plans from repository
        // mealPlans = dietaryRepository.getMealPlans()
        isLoading = false
    }

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
                )
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
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(paddingValues),
                contentAlignment = Alignment.Center
            ) {
                Text("Error: $errorMessage")
            }
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
                        text = "Quick Actions",
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    
                    Spacer(modifier = Modifier.height(8.dp))
                    
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        QuickActionCard(
                            icon = Icons.Default.Search,
                            label = "Recipes",
                            onClick = onNavigateToRecipeSearch,
                            modifier = Modifier.weight(1f)
                        )
                        
                        QuickActionCard(
                            icon = Icons.Default.AutoAwesome,
                            label = "AI Tips",
                            onClick = onNavigateToAiRecommendations,
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
    mealPlan: com.nutriplan.shared.data.model.MealPlan,
    onClick: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            // F11: Add accessible name for screen readers (WCAG 4.1.2)
            .semantics { contentDescription = "${mealPlan.name}, ${mealPlan.startDate} to ${mealPlan.endDate}" }
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
                text = "${mealPlan.startDate} - ${mealPlan.endDate}",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.64f) // WCAG AA: ≥0.54 for normal text (F2)
            )
            
            Spacer(modifier = Modifier.height(8.dp))
            
            Text(
                text = "Calories: ${mealPlan.targetCalories ?: "-"} kcal/day",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.64f) // WCAG AA: ≥0.54 for normal text (F2)
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
            // F19: Use defaultMinSize instead of fixed height to prevent text clipping at large dynamic type (WCAG 1.4.4)
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
