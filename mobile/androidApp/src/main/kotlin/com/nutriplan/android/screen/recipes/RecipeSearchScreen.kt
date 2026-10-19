@file:OptIn(
    androidx.compose.material3.ExperimentalMaterial3Api::class,
    androidx.compose.foundation.layout.ExperimentalLayoutApi::class,
)

package com.nutriplan.android.screen.recipes

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.nutriplan.android.R
import com.nutriplan.android.component.EmptyState
import com.nutriplan.android.di.koinInject
import com.nutriplan.android.i18n.dietTypeLabelRes
import com.nutriplan.android.i18n.messageRes
import com.nutriplan.shared.data.model.Recipe
import com.nutriplan.shared.recipes.RecipeListError
import com.nutriplan.shared.recipes.RecipeSearchUiState
import com.nutriplan.shared.recipes.RecipeSearchViewModel
import kotlinx.coroutines.launch

/** Test tags for the recipe search screen (used by the Robolectric UI tests). */
object RecipeSearchTestTags {
    const val LIST = "recipe_search_list"
    const val INGREDIENTS = "recipe_search_ingredients"
    const val MAX_CALORIES = "recipe_search_max_calories"
    const val MIN_PROTEIN = "recipe_search_min_protein"
    const val SEARCH = "recipe_search_submit"
    const val CLEAR = "recipe_search_clear"
    const val LOADING = "recipe_search_loading"
    const val LOAD_MORE = "recipe_search_load_more"
    const val ERROR_BANNER = "recipe_search_error_banner"
    const val RECIPE_CARD = "recipe_search_card"
    const val DIET_CHIP = "recipe_search_diet_chip"
}

/**
 * DPL-601: search the recipe catalog by ingredients, diet, calories and protein, with images in the
 * results. [onRecipeClick] opens a recipe (when [isPicking], the user is choosing one to add to a plan); [onSessionExpired] is called when the server rejects the
 * session so the app can send the user back to sign-in.
 */
@Composable
fun RecipeSearchScreen(
    onBack: () -> Unit,
    onRecipeClick: (recipeId: String) -> Unit,
    onSessionExpired: () -> Unit,
    isPicking: Boolean = false,
) {
    val viewModel = koinInject<RecipeSearchViewModel>()
    val state by viewModel.state.collectAsState()
    val scope = rememberCoroutineScope()

    // Show the catalog straight away; the filters narrow it down.
    LaunchedEffect(viewModel) { viewModel.search() }
    LaunchedEffect(state.error) {
        if (state.error == RecipeListError.SESSION_EXPIRED) onSessionExpired()
    }

    RecipeSearchScreenContent(
        state = state,
        onIngredientsChange = viewModel::onIngredientsChange,
        onDietTypeChange = viewModel::onDietTypeChange,
        onMaxCaloriesChange = viewModel::onMaxCaloriesChange,
        onMinProteinChange = viewModel::onMinProteinChange,
        onSearch = { scope.launch { viewModel.search() } },
        onClearFilters = {
            viewModel.clearFilters()
            scope.launch { viewModel.search() }
        },
        onLoadMore = { scope.launch { viewModel.loadMore() } },
        onRecipeClick = onRecipeClick,
        onBack = onBack,
        isPicking = isPicking,
    )
}

/** Stateless recipe search: renders [state]; every action is a callback. */
@Composable
fun RecipeSearchScreenContent(
    state: RecipeSearchUiState,
    onIngredientsChange: (String) -> Unit,
    onDietTypeChange: (String?) -> Unit,
    onMaxCaloriesChange: (String) -> Unit,
    onMinProteinChange: (String) -> Unit,
    onSearch: () -> Unit,
    onClearFilters: () -> Unit,
    onLoadMore: () -> Unit,
    onRecipeClick: (String) -> Unit,
    onBack: () -> Unit,
    isPicking: Boolean = false,
) {
    val loadingDescription = stringResource(R.string.cd_recipes_loading)
    val loadingMoreDescription = stringResource(R.string.cd_recipes_loading_more)

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = stringResource(if (isPicking) R.string.recipes_pick_title else R.string.recipes_title),
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
                .testTag(RecipeSearchTestTags.LIST),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item(key = "filters") {
                Filters(
                    state = state,
                    onIngredientsChange = onIngredientsChange,
                    onDietTypeChange = onDietTypeChange,
                    onMaxCaloriesChange = onMaxCaloriesChange,
                    onMinProteinChange = onMinProteinChange,
                    onSearch = onSearch,
                    onClearFilters = onClearFilters,
                )
            }

            val error = state.error
            if (error != null) {
                item(key = "error") {
                    Text(
                        text = stringResource(error.messageRes()),
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier
                            .testTag(RecipeSearchTestTags.ERROR_BANNER)
                            .semantics { liveRegion = LiveRegionMode.Polite },
                    )
                }
            }

            if (state.isLoading) {
                item(key = "loading") {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(24.dp)
                            .testTag(RecipeSearchTestTags.LOADING),
                        contentAlignment = Alignment.Center,
                    ) {
                        CircularProgressIndicator(
                            modifier = Modifier.semantics { contentDescription = loadingDescription },
                        )
                    }
                }
            } else {
                if (state.isEmptyResult) {
                    item(key = "empty") {
                        EmptyState(
                            title = stringResource(R.string.recipes_empty_title),
                            description = stringResource(R.string.recipes_empty_description),
                        )
                    }
                }

                items(state.recipes, key = { it.id }) { recipe ->
                    RecipeCard(recipe = recipe, onClick = { onRecipeClick(recipe.id) })
                }

                if (state.isLoadingMore) {
                    item(key = "loading-more") {
                        Box(modifier = Modifier.fillMaxWidth().padding(8.dp), contentAlignment = Alignment.Center) {
                            CircularProgressIndicator(
                                modifier = Modifier
                                    .size(28.dp)
                                    .semantics { contentDescription = loadingMoreDescription },
                            )
                        }
                    }
                } else if (state.hasMore) {
                    item(key = "more") {
                        OutlinedButton(
                            onClick = onLoadMore,
                            modifier = Modifier
                                .fillMaxWidth()
                                .heightIn(min = 48.dp)
                                .testTag(RecipeSearchTestTags.LOAD_MORE),
                        ) {
                            Text(stringResource(R.string.recipes_load_more))
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun Filters(
    state: RecipeSearchUiState,
    onIngredientsChange: (String) -> Unit,
    onDietTypeChange: (String?) -> Unit,
    onMaxCaloriesChange: (String) -> Unit,
    onMinProteinChange: (String) -> Unit,
    onSearch: () -> Unit,
    onClearFilters: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        OutlinedTextField(
            value = state.ingredients,
            onValueChange = onIngredientsChange,
            label = { Text(stringResource(R.string.recipes_filter_ingredients_label)) },
            supportingText = { Text(stringResource(R.string.recipes_filter_ingredients_hint)) },
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            modifier = Modifier
                .fillMaxWidth()
                .testTag(RecipeSearchTestTags.INGREDIENTS),
        )

        Text(
            text = stringResource(R.string.recipes_filter_diet_label),
            style = MaterialTheme.typography.labelLarge,
        )
        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier.fillMaxWidth(),
        ) {
            DietChip(
                label = stringResource(R.string.recipes_filter_diet_any),
                selected = state.dietType == null,
                onClick = { onDietTypeChange(null) },
            )
            RecipeSearchViewModel.DIET_TYPES.forEach { type ->
                DietChip(
                    label = dietTypeLabelRes(type)?.let { stringResource(it) } ?: type,
                    selected = state.dietType == type,
                    onClick = { onDietTypeChange(type) },
                )
            }
        }

        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            OutlinedTextField(
                value = state.maxCalories,
                onValueChange = onMaxCaloriesChange,
                label = { Text(stringResource(R.string.recipes_filter_max_calories_label)) },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number, imeAction = ImeAction.Next),
                modifier = Modifier
                    .weight(1f)
                    .testTag(RecipeSearchTestTags.MAX_CALORIES),
            )
            OutlinedTextField(
                value = state.minProtein,
                onValueChange = onMinProteinChange,
                label = { Text(stringResource(R.string.recipes_filter_min_protein_label)) },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal, imeAction = ImeAction.Search),
                modifier = Modifier
                    .weight(1f)
                    .testTag(RecipeSearchTestTags.MIN_PROTEIN),
            )
        }

        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
            Button(
                onClick = onSearch,
                enabled = !state.isLoading,
                modifier = Modifier
                    .weight(1f)
                    .heightIn(min = 48.dp)
                    .testTag(RecipeSearchTestTags.SEARCH),
            ) {
                Text(stringResource(R.string.recipes_search))
            }
            if (state.hasFilters) {
                OutlinedButton(
                    onClick = onClearFilters,
                    modifier = Modifier
                        .heightIn(min = 48.dp)
                        .testTag(RecipeSearchTestTags.CLEAR),
                ) {
                    Text(stringResource(R.string.recipes_clear_filters))
                }
            }
        }
    }
}

@Composable
private fun DietChip(label: String, selected: Boolean, onClick: () -> Unit) {
    FilterChip(
        selected = selected,
        onClick = onClick,
        label = { Text(label) },
        modifier = Modifier
            .testTag(RecipeSearchTestTags.DIET_CHIP)
            .semantics { this.selected = selected },
    )
}

@Composable
private fun RecipeCard(recipe: Recipe, onClick: () -> Unit) {
    Card(
        onClick = onClick,
        modifier = Modifier
            .fillMaxWidth()
            .testTag(RecipeSearchTestTags.RECIPE_CARD)
            .semantics(mergeDescendants = true) {},
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (!recipe.imageUrl.isNullOrBlank()) {
                // Decorative: the name next to it says what the dish is.
                AsyncImage(
                    model = recipe.imageUrl,
                    contentDescription = null,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier
                        .size(72.dp)
                        .clip(MaterialTheme.shapes.medium),
                )
            }
            Column(modifier = Modifier.weight(1f)) {
                Text(text = recipe.name, style = MaterialTheme.typography.titleMedium)
                val summary = recipeSummary(recipe)
                if (summary.isNotEmpty()) {
                    Text(
                        text = summary,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

/** "30 min · 520 kcal · 32 g protein": whatever the recipe has, nothing for what it lacks. */
@Composable
private fun recipeSummary(recipe: Recipe): String {
    val minutes = recipeTotalMinutes(recipe)
    val info = recipe.nutritionalInfo
    return listOfNotNull(
        minutes?.let { stringResource(R.string.recipe_minutes, it) },
        info?.calories?.let { stringResource(R.string.recipe_kcal, it) },
        info?.protein?.let { stringResource(R.string.recipe_protein_g, formatQuantity(it)) },
    ).joinToString(" · ")
}

/** Prep plus cook time, or whichever of the two is known. */
internal fun recipeTotalMinutes(recipe: Recipe): Int? {
    val prep = recipe.prepTime
    val cook = recipe.cookTime
    return when {
        prep == null && cook == null -> null
        else -> (prep ?: 0) + (cook ?: 0)
    }
}

/** "2" for 2.0 and "1.5" for 1.5, so whole quantities have no trailing ".0". */
internal fun formatQuantity(value: Double): String =
    if (value % 1.0 == 0.0) value.toInt().toString() else value.toString()
