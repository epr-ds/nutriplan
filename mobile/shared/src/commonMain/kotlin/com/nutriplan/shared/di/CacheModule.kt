package com.nutriplan.shared.di

import app.cash.sqldelight.db.SqlDriver
import com.nutriplan.db.NutriPlanDatabase
import com.nutriplan.shared.data.local.DatabaseDriverFactory
import com.nutriplan.shared.data.local.FavoriteRecipeCache
import com.nutriplan.shared.data.local.PendingMealStore
import com.nutriplan.shared.data.local.MealPlanCache
import com.nutriplan.shared.data.repository.AuthRepository
import com.nutriplan.shared.data.repository.CachedDietaryRepository
import com.nutriplan.shared.data.repository.DietaryRepository
import com.nutriplan.shared.data.repository.DietaryRepositoryImpl
import com.nutriplan.shared.data.repository.FavoriteRecipesRemoteImpl
import com.nutriplan.shared.data.repository.FavoriteRecipesRepository
import com.nutriplan.shared.data.repository.MealQueueFlusher
import com.nutriplan.shared.data.repository.PendingMealSync
import com.nutriplan.shared.data.repository.SyncScheduler
import com.nutriplan.shared.recipes.FavoriteRecipesViewModel
import com.nutriplan.shared.session.SignOut
import org.koin.core.module.Module
import org.koin.dsl.module

/**
 * Koin module for the on-device database and everything built on it.
 *
 * Register it after [dataModule]: it replaces the plain [DietaryRepository] with
 * [CachedDietaryRepository], so meal plans are served from the local cache when the server
 * cannot be reached, provides the favorite recipes (DPL-607) with their own local copy, and adds
 * [SignOut], which wipes the session and the caches together.
 */
fun cacheModule(driverFactory: DatabaseDriverFactory): Module =
    cacheModuleFor { driverFactory.createDriver() }

/** Same as [cacheModule] with the SQLite driver supplied directly (used by JVM tests). */
internal fun cacheModuleFor(createDriver: () -> SqlDriver): Module = module {
    single { NutriPlanDatabase(createDriver()) }
    single { MealPlanCache(get()) }
    single { FavoriteRecipeCache(get()) }
    single { PendingMealStore(get()) }
    single<DietaryRepository> {
        CachedDietaryRepository(remote = DietaryRepositoryImpl(), cache = get(), pending = get())
    }
    single {
        PendingMealSync(
            remote = DietaryRepositoryImpl(),
            store = get(),
            cache = get(),
            // The platform module may provide a scheduler that sends the queue in the background.
            scheduler = getOrNull<SyncScheduler>() ?: SyncScheduler.None,
        )
    }
    single<MealQueueFlusher> { get<PendingMealSync>() }
    single { FavoriteRecipesRepository(remote = FavoriteRecipesRemoteImpl(), cache = get()) }
    // One instance for the whole app: a heart toggled on one screen is already filled on the others.
    single { FavoriteRecipesViewModel(repository = get()) }
    single {
        SignOut(
            authRepository = get<AuthRepository>(),
            mealPlanCache = get(),
            favorites = get(),
            pendingMeals = get(),
        )
    }
}
