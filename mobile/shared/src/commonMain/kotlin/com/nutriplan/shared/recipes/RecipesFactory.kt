package com.nutriplan.shared.recipes

import org.koin.mp.KoinPlatform

/**
 * App-facing factories for the recipe screens (DPL-602 / DPL-604).
 *
 * The Compose screens get their view models from Koin (see `recipesModule`); the iOS app, which has
 * no Koin lookup from Swift, gets them from here. Both point at the same default dependencies, so
 * behaviour is shared across platforms by construction.
 */
fun createRecipeSearchViewModel(): RecipeSearchViewModel = KoinPlatform.getKoin().get<RecipeSearchViewModel>()

fun createRecipeDetailViewModel(): RecipeDetailViewModel = KoinPlatform.getKoin().get<RecipeDetailViewModel>()

fun createFavoriteRecipesViewModel(): FavoriteRecipesViewModel = KoinPlatform.getKoin().get<FavoriteRecipesViewModel>()