package com.nutriplan.shared.di

import app.cash.sqldelight.db.SqlDriver
import com.nutriplan.db.NutriPlanDatabase
import com.nutriplan.shared.data.local.DatabaseDriverFactory
import com.nutriplan.shared.data.local.MealPlanCache
import com.nutriplan.shared.data.repository.AuthRepository
import com.nutriplan.shared.data.repository.CachedDietaryRepository
import com.nutriplan.shared.data.repository.DietaryRepository
import com.nutriplan.shared.data.repository.DietaryRepositoryImpl
import com.nutriplan.shared.session.SignOut
import org.koin.core.module.Module
import org.koin.dsl.module

/**
 * Koin module for the on-device database and everything built on it.
 *
 * Register it after [dataModule]: it replaces the plain [DietaryRepository] with
 * [CachedDietaryRepository], so meal plans are served from the local cache when the server
 * cannot be reached, and adds [SignOut], which wipes the session and the cache together.
 */
fun cacheModule(driverFactory: DatabaseDriverFactory): Module =
    cacheModuleFor { driverFactory.createDriver() }

/** Same as [cacheModule] with the SQLite driver supplied directly (used by JVM tests). */
internal fun cacheModuleFor(createDriver: () -> SqlDriver): Module = module {
    single { MealPlanCache(NutriPlanDatabase(createDriver())) }
    single<DietaryRepository> { CachedDietaryRepository(remote = DietaryRepositoryImpl(), cache = get()) }
    single { SignOut(authRepository = get<AuthRepository>(), mealPlanCache = get()) }
}
