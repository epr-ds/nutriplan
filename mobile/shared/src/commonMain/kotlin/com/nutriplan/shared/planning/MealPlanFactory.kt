package com.nutriplan.shared.planning

import org.koin.mp.KoinPlatform

/**
 * App-facing factories for the meal-plan screens (DPL-502 / DPL-505).
 *
 * The Compose screens get their view models from Koin (see `planningModule`); the iOS app, which has
 * no Koin lookup from Swift, gets them from here. Both point at the same default dependencies, so
 * behaviour is shared across platforms by construction.
 */
fun createMealPlanListViewModel(): MealPlanListViewModel = KoinPlatform.getKoin().get<MealPlanListViewModel>()

fun createMealPlanDetailViewModel(): MealPlanDetailViewModel = KoinPlatform.getKoin().get<MealPlanDetailViewModel>()