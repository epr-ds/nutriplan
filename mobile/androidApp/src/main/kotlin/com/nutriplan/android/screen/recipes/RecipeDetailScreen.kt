@file:OptIn(
    androidx.compose.material3.ExperimentalMaterial3Api::class,
    androidx.compose.foundation.layout.ExperimentalLayoutApi::class,
)

package com.nutriplan.android.screen.recipes

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.nutriplan.android.R
import com.nutriplan.android.component.ErrorState
import com.nutriplan.android.di.koinInject
import com.nutriplan.android.i18n.dietTypeLabelRes
import com.nutriplan.android.i18n.messageRes
import com.nutriplan.shared.data.model.NutritionDisclaimer
import com.nutriplan.shared.data.model.Recipe
import com.nutriplan.shared.data.model.RecipeIngredient
import com.nutriplan.shared.recipes.RecipeDetailError
import com.nutriplan.shared.recipes.RecipeDetailUiState
import com.nutriplan.shared.recipes.RecipeDetailViewModel
import kotlinx.coroutines.launch

/** Test tags for the recipe detail screen (used by the Robolectric UI tests). */
object RecipeDetailTestTags {
    const val CONTENT = "recipe_detail_content"
    const val LOADING = "recipe_detail_loading"
    const val NUTRITION = "recipe_detail_nutrition"
    const val DISCLAIMER = "recipe_detail_disclaimer"
    const val INGREDIENT = "recipe_detail_ingredient"
    const val STEP = "recipe_detail_step"
    const val SOURCE = "recipe_detail_source"
}

/**
 * DPL-603: one recipe with its ingredients, steps, nutrition per serving and the nutrition
 * disclaimer. [onSessionExpired] is called when the server rejects the session.
 */
@Composable
fun RecipeDetailScreen(
    recipeId: String,
    onBack: () -> Unit,
    onSessionExpired: () -> Unit,
) {
    val viewModel = koinInject<RecipeDetailViewModel>()
    val state by viewModel.state.collectAsState()
    val scope = rememberCoroutineScope()

    LaunchedEffect(viewModel, recipeId) { viewModel.load(recipeId) }
    LaunchedEffect(state.error) {
        if (state.error == RecipeDetailError.SESSION_EXPIRED) onSessionExpired()
    }

    RecipeDetailScreenContent(
        state = state,
        onRetry = { scope.launch { viewModel.load(recipeId) } },
        onBack = onBack,
    )
}

/** Stateless recipe detail: renders [state]; every action is a callback. */
@Composable
fun RecipeDetailScreenContent(
    state: RecipeDetailUiState,
    onRetry: () -> Unit,
    onBack: () -> Unit,
) {
    val recipe = state.recipe
    val error = state.error
    val loadingDescription = stringResource(R.string.cd_recipe_loading)

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = recipe?.name ?: stringResource(R.string.recipe_detail_title_fallback),
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
            recipe != null -> RecipeContent(recipe = recipe, disclaimer = state.disclaimer, modifier = content)

            state.isLoading -> Box(
                modifier = content.testTag(RecipeDetailTestTags.LOADING),
                contentAlignment = Alignment.Center,
            ) {
                CircularProgressIndicator(
                    modifier = Modifier.semantics { contentDescription = loadingDescription },
                )
            }

            error != null -> ErrorState(
                message = stringResource(error.messageRes()),
                // A recipe that no longer exists cannot be retried: the action goes back instead.
                onRetry = if (error == RecipeDetailError.NOT_FOUND) onBack else onRetry,
                modifier = content,
                actionLabel = stringResource(
                    if (error == RecipeDetailError.NOT_FOUND) {
                        R.string.recipe_detail_back_to_recipes
                    } else {
                        R.string.meal_plans_retry
                    },
                ),
            )
        }
    }
}

@Composable
private fun RecipeContent(
    recipe: Recipe,
    disclaimer: NutritionDisclaimer?,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .verticalScroll(rememberScrollState())
            .testTag(RecipeDetailTestTags.CONTENT),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        if (!recipe.imageUrl.isNullOrBlank()) {
            // Decorative: the title above it says what the dish is.
            AsyncImage(
                model = recipe.imageUrl,
                contentDescription = null,
                contentScale = ContentScale.Crop,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(200.dp),
            )
        }

        Column(
            modifier = Modifier.padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Overview(recipe)

            recipe.nutritionalInfo?.let { info ->
                // Nutrition is never shown on its own: the disclaimer always follows it.
                NutritionCard(info = info)
            }
            DisclaimerCard(disclaimer)

            if (recipe.ingredients.isNotEmpty()) {
                SectionTitle(stringResource(R.string.recipe_detail_ingredients))
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    recipe.ingredients.forEach { ingredient ->
                        Text(
                            text = ingredientLine(ingredient),
                            style = MaterialTheme.typography.bodyLarge,
                            modifier = Modifier.testTag(RecipeDetailTestTags.INGREDIENT),
                        )
                    }
                }
            }

            if (recipe.instructions.isNotEmpty()) {
                SectionTitle(stringResource(R.string.recipe_detail_instructions))
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    recipe.instructions.forEachIndexed { index, step ->
                        Text(
                            text = stringResource(R.string.recipe_detail_step, index + 1, step),
                            style = MaterialTheme.typography.bodyLarge,
                            modifier = Modifier.testTag(RecipeDetailTestTags.STEP),
                        )
                    }
                }
            }

            Box(modifier = Modifier.height(16.dp))
        }
    }
}

@Composable
private fun Overview(recipe: Recipe) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        recipe.description?.takeIf { it.isNotBlank() }?.let {
            Text(text = it, style = MaterialTheme.typography.bodyLarge)
        }

        val facts = listOfNotNull(
            recipe.prepTime?.let { stringResource(R.string.recipe_detail_prep, it) },
            recipe.cookTime?.let { stringResource(R.string.recipe_detail_cook, it) },
            recipe.servings?.let { stringResource(R.string.recipe_detail_servings, it) },
        )
        if (facts.isNotEmpty()) {
            Text(
                text = facts.joinToString(" · "),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        if (recipe.dietaryTypes.isNotEmpty()) {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                recipe.dietaryTypes.forEach { type ->
                    AssistChip(
                        onClick = {},
                        enabled = false,
                        label = { Text(dietTypeLabelRes(type)?.let { stringResource(it) } ?: type) },
                    )
                }
            }
        }
    }
}

@Composable
private fun NutritionCard(info: com.nutriplan.shared.data.model.NutritionalInfo) {
    val lines = listOfNotNull(
        info.calories?.let { stringResource(R.string.recipe_kcal, it) },
        info.protein?.let { stringResource(R.string.recipe_nutrition_protein, formatQuantity(it)) },
        info.carbs?.let { stringResource(R.string.recipe_nutrition_carbs, formatQuantity(it)) },
        info.fat?.let { stringResource(R.string.recipe_nutrition_fat, formatQuantity(it)) },
        info.sugar?.let { stringResource(R.string.recipe_nutrition_sugar, formatQuantity(it)) },
    )
    if (lines.isEmpty()) return

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .testTag(RecipeDetailTestTags.NUTRITION)
            .semantics(mergeDescendants = true) {},
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(
                text = stringResource(R.string.recipe_detail_nutrition_title),
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.semantics { heading() },
            )
            lines.forEach { Text(text = it, style = MaterialTheme.typography.bodyLarge) }
        }
    }
}

/**
 * The nutrition disclaimer. The server's text and sources are used when they loaded; otherwise the
 * bundled text, so the values above are never shown without one.
 */
@Composable
private fun DisclaimerCard(disclaimer: NutritionDisclaimer?) {
    val uriHandler = LocalUriHandler.current

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .testTag(RecipeDetailTestTags.DISCLAIMER),
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(
                text = stringResource(R.string.recipe_detail_disclaimer_title),
                style = MaterialTheme.typography.titleSmall,
                modifier = Modifier.semantics { heading() },
            )
            Text(
                text = disclaimer?.disclaimer?.takeIf { it.isNotBlank() }
                    ?: stringResource(R.string.recipe_disclaimer_fallback),
                style = MaterialTheme.typography.bodyMedium,
            )

            val sources = disclaimer?.sources.orEmpty()
            if (sources.isNotEmpty()) {
                Text(
                    text = stringResource(R.string.recipe_disclaimer_sources),
                    style = MaterialTheme.typography.labelLarge,
                )
                sources.forEach { source ->
                    val label = if (source.verified) {
                        stringResource(R.string.recipe_disclaimer_source_verified, source.name)
                    } else {
                        source.name
                    }
                    // Only web links are opened; anything else is shown as plain text.
                    if (source.url.startsWith("https://") || source.url.startsWith("http://")) {
                        TextButton(
                            onClick = { uriHandler.openUri(source.url) },
                            modifier = Modifier.testTag(RecipeDetailTestTags.SOURCE),
                        ) { Text(label) }
                    } else {
                        Text(text = label, style = MaterialTheme.typography.bodyMedium)
                    }
                }
            }

            disclaimer?.lastReviewed?.takeIf { it.isNotBlank() }?.let {
                Text(
                    text = stringResource(R.string.recipe_disclaimer_reviewed, it),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun SectionTitle(text: String) {
    Text(
        text = text,
        style = MaterialTheme.typography.titleMedium,
        modifier = Modifier.semantics { heading() },
    )
}

/** "200 g chicken breast", "2 eggs" or just "salt" when the amount is unknown. */
private fun ingredientLine(ingredient: RecipeIngredient): String {
    val amount = ingredient.quantity?.let { formatQuantity(it) }
    return listOfNotNull(amount, ingredient.unit?.takeIf { it.isNotBlank() }, ingredient.name).joinToString(" ")
}
