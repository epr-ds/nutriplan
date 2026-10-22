package com.nutriplan.shared.di

import com.nutriplan.shared.ai.AiRecommendationsViewModel
import com.nutriplan.shared.ai.AnalyzeMealViewModel
import com.nutriplan.shared.ai.OptimizePlanViewModel
import com.nutriplan.shared.recipes.RecipeDetailViewModel
import com.nutriplan.shared.recipes.RecipeSearchViewModel
import com.nutriplan.shared.session.SessionManager
import com.nutriplan.shared.session.SessionState
import org.koin.dsl.module

/**
 * Koin module for the recipe screens (DPL-601, DPL-603), the AI recommendations (AIA-602), the
 * plan optimization (AIA-605) and the meal analysis (AIA-607).
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
    // AIA-605: the plan is read and its meals updated through the (cached) Dietary repository.
    factory { OptimizePlanViewModel(advisor = get(), plans = get()) }
    factory { AnalyzeMealViewModel(advisor = get()) }
}