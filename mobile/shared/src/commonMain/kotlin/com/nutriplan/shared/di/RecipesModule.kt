package com.nutriplan.shared.di

import com.nutriplan.shared.recipes.RecipeDetailViewModel
import com.nutriplan.shared.recipes.RecipeSearchViewModel
import org.koin.dsl.module

/**
 * Koin module for the recipe screens (DPL-601, DPL-603).
 *
 * View-models are `factory` definitions: each screen gets its own state holder.
 */
val recipesModule = module {
    factory { RecipeSearchViewModel(repository = get()) }
    factory { RecipeDetailViewModel(repository = get()) }
}
