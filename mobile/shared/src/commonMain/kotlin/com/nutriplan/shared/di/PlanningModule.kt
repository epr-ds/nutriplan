package com.nutriplan.shared.di

import com.nutriplan.shared.planning.MealPlanListViewModel
import org.koin.dsl.module

/**
 * Koin module for the meal planning feature (DPL-5xx).
 *
 * View-models are `factory` definitions: each screen gets its own state holder.
 */
val planningModule = module {
    factory { MealPlanListViewModel(repository = get()) }
}
