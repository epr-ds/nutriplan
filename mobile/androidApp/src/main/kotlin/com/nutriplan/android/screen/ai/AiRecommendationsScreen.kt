@file:OptIn(
    androidx.compose.material3.ExperimentalMaterial3Api::class,
    androidx.compose.foundation.layout.ExperimentalLayoutApi::class,
)

package com.nutriplan.android.screen.ai

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
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
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import com.nutriplan.android.R
import com.nutriplan.android.component.EmptyState
import com.nutriplan.android.di.koinInjectRetained
import com.nutriplan.android.i18n.mealTypeLabelRes
import com.nutriplan.android.i18n.recommendationsMessageRes
import com.nutriplan.android.screen.recipes.RecipeCard
import com.nutriplan.shared.ai.AiError
import com.nutriplan.shared.ai.AiLoadingStage
import com.nutriplan.shared.ai.AiRecommendationsUiState
import com.nutriplan.shared.ai.AiRecommendationsViewModel
import com.nutriplan.shared.data.model.NutritionalAlignment
import com.nutriplan.shared.data.model.Recipe
import kotlinx.coroutines.launch
import kotlin.math.roundToInt

/** Test tags for the AI recommendations screen (used by the Robolectric UI tests). */
object AiRecommendationsTestTags {
    const val LIST = "ai_recommendations_list"
    const val MEAL_TYPE_CHIP = "ai_recommendations_meal_type_chip"
    const val INGREDIENTS = "ai_recommendations_ingredients"
    const val SUBMIT = "ai_recommendations_submit"
    const val LOADING = "ai_recommendations_loading"
    const val ERROR_BANNER = "ai_recommendations_error_banner"
    const val CURATED_FALLBACK_NOTE = "ai_recommendations_curated_fallback_note"
    const val REASONING = "ai_recommendations_reasoning"
    const val ALIGNMENT = "ai_recommendations_alignment"
    const val DISCLAIMER = "ai_recommendations_disclaimer"
    const val EMPTY = "ai_recommendations_empty"
    const val ADD_TO_PLAN = "ai_recommendations_add_to_plan"
    const val ADDED_NOTICE = "ai_recommendations_added_notice"
}

/**
 * AIA-602: recipes the AI Advisor recommends for the user's saved dietary preferences, optionally
 * for one meal and the ingredients on hand, with why they fit, how well they match the targets and
 * the medical disclaimer. Asks straight away on opening. [onRecipeClick] opens a recipe;
 * [onSessionExpired] is called when the server rejects the session.
 *
 * AIA-604: [onAddToPlan] starts adding a recommendation to a plan, for the meal the answer was asked
 * for. [mealAdded] confirms that one was added; [onMealAddedShown] is called when the user asks again.
 *
 * When the AI could not produce a usable answer and curated catalogue recipes were served instead
 * (AIA-503), a note says so above the recipes.
 */
@Composable
fun AiRecommendationsScreen(
    onBack: () -> Unit,
    onRecipeClick: (recipeId: String) -> Unit,
    onSessionExpired: () -> Unit,
    onAddToPlan: (recipeId: String, mealType: String?) -> Unit,
    mealAdded: Boolean = false,
    onMealAddedShown: () -> Unit = {},
    /** AIA-606: the non-AI way to find recipes, offered when the AI cannot answer. */
    onBrowseRecipes: (() -> Unit)? = null,
) {
    // Kept while the user adds a recommendation to a plan, so coming back does not ask again.
    val viewModel = koinInjectRetained<AiRecommendationsViewModel>()
    val state by viewModel.state.collectAsState()
    val scope = rememberCoroutineScope()

    LaunchedEffect(viewModel) { if (!viewModel.state.value.hasRequested) viewModel.recommend() }
    LaunchedEffect(state.error) {
        if (state.error == AiError.SESSION_EXPIRED) onSessionExpired()
    }

    AiRecommendationsScreenContent(
        state = state,
        onMealTypeChange = viewModel::onMealTypeChange,
        onIngredientsChange = viewModel::onIngredientsChange,
        onRecommend = {
            onMealAddedShown()
            scope.launch { viewModel.recommend() }
        },
        onRecipeClick = onRecipeClick,
        onBack = onBack,
        onAddToPlan = { recipe -> onAddToPlan(recipe.id, state.resultMealType) },
        mealAdded = mealAdded,
        loadingStage = rememberAiLoadingStage(state.isLoading),
        onBrowseRecipes = onBrowseRecipes,
    )
}

/** Stateless AI recommendations: renders [state]; every action is a callback. */
@Composable
fun AiRecommendationsScreenContent(
    state: AiRecommendationsUiState,
    onMealTypeChange: (String?) -> Unit,
    onIngredientsChange: (String) -> Unit,
    onRecommend: () -> Unit,
    onRecipeClick: (String) -> Unit,
    onBack: () -> Unit,
    /** Shows an "Add to plan" button under each recommendation when set (AIA-604). */
    onAddToPlan: ((Recipe) -> Unit)? = null,
    /** Confirms that a recommendation was just added to a plan. */
    mealAdded: Boolean = false,
    /** How long the request has been running (AIA-606). */
    loadingStage: AiLoadingStage = AiLoadingStage.STARTED,
    /** Offered next to the retry when the AI cannot answer (AIA-606). */
    onBrowseRecipes: (() -> Unit)? = null,
) {
    val loadingDescription = stringResource(R.string.cd_ai_recommendations_loading)
    val result = state.result

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = stringResource(R.string.ai_recommendations_title),
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
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .testTag(AiRecommendationsTestTags.LIST),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item(key = "request") {
                RequestForm(
                    state = state,
                    onMealTypeChange = onMealTypeChange,
                    onIngredientsChange = onIngredientsChange,
                    onRecommend = onRecommend,
                )
            }

            if (mealAdded) {
                item(key = "added") {
                    Text(
                        text = stringResource(R.string.ai_recommendations_added),
                        color = MaterialTheme.colorScheme.primary,
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier
                            .testTag(AiRecommendationsTestTags.ADDED_NOTICE)
                            .semantics { liveRegion = LiveRegionMode.Polite },
                    )
                }
            }

            val error = state.error
            if (error != null) {
                item(key = "error") {
                    AiErrorCard(
                        message = stringResource(error.recommendationsMessageRes()),
                        onRetry = onRecommend,
                        messageTestTag = AiRecommendationsTestTags.ERROR_BANNER,
                        retryEnabled = !state.isLoading,
                        // The session error sends the user to sign in; browsing would not help there.
                        fallbackLabel = stringResource(R.string.ai_recommendations_browse_recipes)
                            .takeIf { error != AiError.SESSION_EXPIRED },
                        onFallback = onBrowseRecipes,
                    )
                }
            }

            // Also the moment before the first request has started: the screen asks on opening.
            if (state.isLoading || (!state.hasRequested && error == null)) {
                item(key = "loading") {
                    AiLoadingSkeleton(
                        stage = loadingStage,
                        description = loadingDescription,
                        modifier = Modifier.testTag(AiRecommendationsTestTags.LOADING),
                    )
                }
            } else if (result != null) {
                // Say so when the AI could not answer and curated recipes stand in (AIA-503).
                if (result.isCuratedFallback && result.recommendations.isNotEmpty()) {
                    item(key = "curated-fallback") { CuratedFallbackNote() }
                }
                result.reasoning?.takeIf { it.isNotBlank() }?.let { reasoning ->
                    item(key = "reasoning") { ReasoningCard(reasoning) }
                }
                result.nutritionalAlignment?.takeIf { it.score != null || !it.details.isNullOrBlank() }?.let { alignment ->
                    item(key = "alignment") { AlignmentCard(alignment) }
                }
                if (state.isEmpty) {
                    item(key = "empty") {
                        EmptyState(
                            title = stringResource(R.string.ai_recommendations_empty_title),
                            description = stringResource(R.string.ai_recommendations_empty_description),
                            modifier = Modifier.testTag(AiRecommendationsTestTags.EMPTY),
                        )
                    }
                } else {
                    item(key = "recipes-heading") {
                        Text(
                            text = stringResource(R.string.ai_recommendations_recipes_heading),
                            style = MaterialTheme.typography.titleMedium,
                            modifier = Modifier.semantics { heading() },
                        )
                    }
                }
                items(result.recommendations, key = { it.id }) { recipe ->
                    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        RecipeCard(recipe = recipe, onClick = { onRecipeClick(recipe.id) })
                        if (onAddToPlan != null) AddToPlanButton(recipe, onClick = { onAddToPlan(recipe) })
                    }
                }
                // Required with every AI answer: what is shown is not medical advice.
                item(key = "disclaimer") {
                    AiDisclaimer(
                        result.disclaimer?.takeIf { it.isNotBlank() }
                            ?: stringResource(R.string.ai_disclaimer_fallback),
                    )
                }
            }
        }
    }
}

@Composable
private fun RequestForm(
    state: AiRecommendationsUiState,
    onMealTypeChange: (String?) -> Unit,
    onIngredientsChange: (String) -> Unit,
    onRecommend: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(
            text = stringResource(R.string.ai_recommendations_intro),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            text = stringResource(R.string.ai_recommendations_meal_type_label),
            style = MaterialTheme.typography.labelLarge,
        )
        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier.fillMaxWidth(),
        ) {
            MealTypeChip(
                label = stringResource(R.string.ai_recommendations_meal_type_any),
                selected = state.mealType == null,
                onClick = { onMealTypeChange(null) },
            )
            AiRecommendationsViewModel.MEAL_TYPES.forEach { type ->
                MealTypeChip(
                    label = mealTypeLabelRes(type)?.let { stringResource(it) } ?: type,
                    selected = state.mealType == type,
                    onClick = { onMealTypeChange(type) },
                )
            }
        }
        OutlinedTextField(
            value = state.ingredients,
            onValueChange = onIngredientsChange,
            label = { Text(stringResource(R.string.ai_recommendations_ingredients_label)) },
            supportingText = { Text(stringResource(R.string.ai_recommendations_ingredients_hint)) },
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            keyboardActions = KeyboardActions(onSearch = { if (!state.isLoading) onRecommend() }),
            modifier = Modifier
                .fillMaxWidth()
                .testTag(AiRecommendationsTestTags.INGREDIENTS),
        )
        Button(
            onClick = onRecommend,
            enabled = !state.isLoading,
            modifier = Modifier
                .fillMaxWidth()
                .testTag(AiRecommendationsTestTags.SUBMIT),
        ) {
            Text(stringResource(R.string.ai_recommendations_submit))
        }
    }
}

@Composable
private fun MealTypeChip(label: String, selected: Boolean, onClick: () -> Unit) {
    FilterChip(
        selected = selected,
        onClick = onClick,
        label = { Text(label) },
        modifier = Modifier
            .testTag(AiRecommendationsTestTags.MEAL_TYPE_CHIP)
            .semantics { this.selected = selected },
    )
}

@Composable
private fun ReasoningCard(reasoning: String) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .testTag(AiRecommendationsTestTags.REASONING)
            .semantics(mergeDescendants = true) {
                // AIA-903: the reasoning is the answer's content: announce it, not just the card shape.
                contentDescription = reasoning
            },
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(
                text = stringResource(R.string.ai_recommendations_reasoning_title),
                style = MaterialTheme.typography.titleSmall,
            )
            Text(text = reasoning, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

/** Tells the user these are curated catalogue recipes, not the AI's own answer. */
@Composable
private fun CuratedFallbackNote() {
    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer),
        modifier = Modifier
            .fillMaxWidth()
            .testTag(AiRecommendationsTestTags.CURATED_FALLBACK_NOTE)
            .semantics(mergeDescendants = true) {},
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            // Decorative: the label next to it says the same.
            Icon(
                Icons.Outlined.Info,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.onSecondaryContainer,
            )
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(
                    text = stringResource(R.string.ai_recommendations_curated_fallback_title),
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.onSecondaryContainer,
                )
                Text(
                    text = stringResource(R.string.ai_recommendations_curated_fallback_body),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSecondaryContainer,
                )
            }
        }
    }
}

/** How well an AI answer fits the user's targets: the 0-100 score with a bar, and the details. */
@Composable
internal fun AlignmentCard(alignment: NutritionalAlignment, testTag: String = AiRecommendationsTestTags.ALIGNMENT) {
    // The contract gives the score from 0 to 100.
    val score = alignment.score?.roundToInt()?.coerceIn(0, 100)
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .testTag(testTag)
            .semantics(mergeDescendants = true) {},
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(
                text = stringResource(R.string.ai_recommendations_alignment_title),
                style = MaterialTheme.typography.titleSmall,
            )
            if (score != null) {
                Text(
                    text = stringResource(R.string.ai_recommendations_alignment_score, score),
                    style = MaterialTheme.typography.headlineSmall,
                )
                // Decorative: the number above says the same.
                LinearProgressIndicator(
                    progress = { score / 100f },
                    modifier = Modifier
                        .fillMaxWidth()
                        .clearAndSetSemantics {},
                )
            }
            alignment.details?.takeIf { it.isNotBlank() }?.let { details ->
                Text(text = details, style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}

/** The medical disclaimer every AI answer must be shown with. */
@Composable
internal fun AiDisclaimer(text: String, testTag: String = AiRecommendationsTestTags.DISCLAIMER) {
    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
        modifier = Modifier
            .fillMaxWidth()
            .testTag(testTag),
    ) {
        Text(
            text = text,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(12.dp),
        )
    }
}

@Composable
private fun AddToPlanButton(recipe: Recipe, onClick: () -> Unit) {
    val description = stringResource(R.string.cd_ai_recommendations_add_to_plan, recipe.name)
    OutlinedButton(
        onClick = onClick,
        modifier = Modifier
            .fillMaxWidth()
            .testTag(AiRecommendationsTestTags.ADD_TO_PLAN)
            // Says which recipe: every recommendation has the same button.
            .semantics { contentDescription = description },
    ) {
        Text(stringResource(R.string.ai_recommendations_add_to_plan))
    }
}
