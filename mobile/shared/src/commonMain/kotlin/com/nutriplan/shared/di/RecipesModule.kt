package com.nutriplan.shared.di

import com.nutriplan.shared.ai.AiRecommendationsViewModel
import com.nutriplan.shared.recipes.RecipeDetailViewModel
import com.nutriplan.shared.recipes.RecipeSearchViewModel
import com.nutriplan.shared.session.SessionManager
import com.nutriplan.shared.session.SessionState
import org.koin.dsl.module

/**
 * Koin module for the recipe screens (DPL-601, DPL-603) and the AI recommendations (AIA-602).
 *
 * View-models are `factory` definitions: each screen gets its own state holder.
 */
val recipesModule = module {
    factory { RecipeSearchViewModel(repository = get()) }
    factory { RecipeDetailViewModel(repository = get()) }
    factory {
        val session = get<SessionManager>()
        AiRecommendationsViewModel(
            advisor = get(),
            // Read at each request: the signed-in user's saved dietary preferences.
            preferences = { (session.state.value as? SessionState.SignedIn)?.user?.dietaryPreferences },
        )
    }
}