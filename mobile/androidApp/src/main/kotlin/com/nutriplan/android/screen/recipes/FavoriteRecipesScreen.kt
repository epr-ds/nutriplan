@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.nutriplan.android.screen.recipes

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.nutriplan.android.R
import com.nutriplan.android.component.EmptyState
import com.nutriplan.android.component.ErrorState
import com.nutriplan.android.di.koinInject
import com.nutriplan.android.i18n.loadMessageRes
import com.nutriplan.shared.data.model.Recipe
import com.nutriplan.shared.recipes.FavoriteError
import com.nutriplan.shared.recipes.FavoriteRecipesUiState
import com.nutriplan.shared.recipes.FavoriteRecipesViewModel
import kotlinx.coroutines.launch

/** Test tags for the favorites list (used by the Robolectric UI tests). */
object FavoriteRecipesTestTags {
    const val LIST = "favorites_list"
    const val LOADING = "favorites_loading"
    const val OFFLINE_NOTE = "favorites_offline_note"
}

/**
 * DPL-607: the recipes the user saved as favorites, most recently saved first. Works from the copy
 * saved on the device when the server cannot be reached. [onRecipeClick] opens a recipe;
 * [onSessionExpired] is called when the server rejects the session.
 */
@Composable
fun FavoriteRecipesScreen(
    onBack: () -> Unit,
    onRecipeClick: (recipeId: String) -> Unit,
    onSessionExpired: () -> Unit,
) {
    val favorites = koinInject<FavoriteRecipesViewModel>()
    val state by favorites.state.collectAsState()
    val scope = rememberCoroutineScope()

    // Always refresh on opening: the list may have changed on another device.
    LaunchedEffect(favorites) { favorites.load() }
    LaunchedEffect(state.loadError, state.changeError) {
        if (state.loadError == FavoriteError.SESSION_EXPIRED || state.changeError == FavoriteError.SESSION_EXPIRED) {
            onSessionExpired()
        }
    }

    FavoriteRecipesScreenContent(
        state = state,
        onRecipeClick = onRecipeClick,
        onToggleFavorite = { recipe -> scope.launch { favorites.toggle(recipe) } },
        onRetry = { scope.launch { favorites.load() } },
        onBack = onBack,
    )
}

/** Stateless favorites list: renders [state]; every action is a callback. */
@Composable
fun FavoriteRecipesScreenContent(
    state: FavoriteRecipesUiState,
    onRecipeClick: (String) -> Unit,
    onToggleFavorite: (Recipe) -> Unit,
    onRetry: () -> Unit,
    onBack: () -> Unit,
) {
    val loadingDescription = stringResource(R.string.cd_favorites_loading)
    val loadError = state.loadError

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = stringResource(R.string.favorites_title),
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
            // First load, nothing to show yet (also the moment before the load has started).
            !state.hasLoaded && loadError == null -> Box(
                modifier = content.testTag(FavoriteRecipesTestTags.LOADING),
                contentAlignment = Alignment.Center,
            ) {
                CircularProgressIndicator(
                    modifier = Modifier.semantics { contentDescription = loadingDescription },
                )
            }

            !state.hasLoaded && loadError != null -> ErrorState(
                message = stringResource(loadError.loadMessageRes()),
                onRetry = onRetry,
                modifier = content,
                actionLabel = stringResource(R.string.meal_plans_retry),
            )

            else -> LazyColumn(
                modifier = content.testTag(FavoriteRecipesTestTags.LIST),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                if (state.isOffline) {
                    item(key = "offline") {
                        Text(
                            text = stringResource(R.string.favorites_offline),
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier
                                .testTag(FavoriteRecipesTestTags.OFFLINE_NOTE)
                                .semantics { liveRegion = LiveRegionMode.Polite },
                        )
                    }
                }
                state.changeError?.let { error ->
                    item(key = "change-error") { FavoriteChangeError(error) }
                }
                if (state.recipes.isEmpty()) {
                    item(key = "empty") {
                        EmptyState(
                            title = stringResource(R.string.favorites_empty_title),
                            description = stringResource(R.string.favorites_empty_description),
                        )
                    }
                }
                items(state.recipes, key = { it.id }) { recipe ->
                    RecipeCard(
                        recipe = recipe,
                        onClick = { onRecipeClick(recipe.id) },
                        favorite = FavoriteAction(
                            isFavorite = true,
                            enabled = recipe.id !in state.pendingIds,
                            onToggle = { onToggleFavorite(recipe) },
                        ),
                    )
                }
            }
        }
    }
}
