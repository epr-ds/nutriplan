package com.nutriplan.shared.di

import com.nutriplan.shared.planning.MealPlanDetailViewModel
import com.nutriplan.shared.planning.MealPlanFormViewModel
import com.nutriplan.shared.planning.MealPlanListViewModel
import com.nutriplan.shared.session.SessionManager
import com.nutriplan.shared.session.SessionState
import org.koin.dsl.module

/**
 * Koin module for the meal planning feature (DPL-5xx).
 *
 * View-models are `factory` definitions: each screen gets its own state holder.
 */
val planningModule = module {
    factory { MealPlanListViewModel(repository = get()) }
    factory { MealPlanDetailViewModel(repository = get()) }
    factory {
        val session = get<SessionManager>()
        MealPlanFormViewModel(
            repository = get(),
            // Read when the form opens: the signed-in user's saved dietary preferences.
            preferences = { (session.state.value as? SessionState.SignedIn)?.user?.dietaryPreferences },
        )
    }
}
