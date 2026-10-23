package com.nutriplan.shared.di

import app.cash.sqldelight.db.SqlDriver
import com.nutriplan.db.NutriPlanDatabase
import com.nutriplan.shared.commerce.AddressBookViewModel
import com.nutriplan.shared.commerce.CheckoutViewModel
import com.nutriplan.shared.commerce.CommerceUseCases
import com.nutriplan.shared.commerce.PaymentMethodsViewModel
import com.nutriplan.shared.commerce.PaymentTokenizer
import com.nutriplan.shared.data.local.DatabaseDriverFactory
import com.nutriplan.shared.data.local.FavoriteRecipeCache
import com.nutriplan.shared.data.local.OrderCache
import com.nutriplan.shared.data.local.PendingChangeStore
import com.nutriplan.shared.data.local.SavedAddressStore
import com.nutriplan.shared.data.local.PendingFavoriteStore
import com.nutriplan.shared.data.local.PendingMealStore
import com.nutriplan.shared.data.local.MealPlanCache
import com.nutriplan.shared.data.repository.AuthRepository
import com.nutriplan.shared.data.repository.CachedDietaryRepository
import com.nutriplan.shared.data.repository.CombinedQueueFlusher
import com.nutriplan.shared.data.repository.CommerceRepository
import com.nutriplan.shared.data.repository.DietaryRepository
import com.nutriplan.shared.data.repository.DietaryRepositoryImpl
import com.nutriplan.shared.data.repository.FavoriteRecipesRemoteImpl
import com.nutriplan.shared.data.repository.FavoriteRecipesRepository
import com.nutriplan.shared.data.repository.MealQueueFlusher
import com.nutriplan.shared.data.repository.OrderRepository
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
    single { PendingChangeStore(get()) }
    single { PendingFavoriteStore(get()) }
    // COM-503: the offline copy of the user's orders and the on-device address book.
    single { OrderCache(get()) }
    single { SavedAddressStore(get()) }
    // COM-504: orders cache-first, then refreshed from the Commerce service; writes go through.
    single { OrderRepository(remote = get<CommerceRepository>(), store = get<OrderCache>(), addresses = get()) }
    // COM-507: the Commerce use cases, one per checkout screen (it remembers unconfirmed orders' keys).
    factory { CommerceUseCases(orders = get(), fulfillment = get(), payments = get()) }
    // COM-601: the address book screen, on the on-device address store.
    factory { AddressBookViewModel(store = get<SavedAddressStore>()) }
    // COM-603: saved payment methods; "Add" needs the platform's provider tokenizer (COM-508).
    factory { PaymentMethodsViewModel(repository = get(), tokenizer = getOrNull<PaymentTokenizer>()) }
    // COM-605: the checkout stepper; plans from the (cached) Dietary client, addresses from the device.
    factory {
        val dietary = get<DietaryRepository>()
        CheckoutViewModel(useCases = get(), loadPlans = { dietary.getMealPlans() }, addressBook = get<SavedAddressStore>())
    }
    single<DietaryRepository> {
        CachedDietaryRepository(remote = DietaryRepositoryImpl(), cache = get(), pending = get(), changes = get())
    }
    single {
        PendingMealSync(
            remote = DietaryRepositoryImpl(),
            store = get(),
            cache = get(),
            // The platform module may provide a scheduler that sends the queue in the background.
            scheduler = getOrNull<SyncScheduler>() ?: SyncScheduler.None,
            changes = get(),
        )
    }
    single {
        FavoriteRecipesRepository(
            remote = FavoriteRecipesRemoteImpl(),
            cache = get(),
            pending = get(),
            scheduler = getOrNull<SyncScheduler>() ?: SyncScheduler.None,
        )
    }
    // The background job sends both offline queues: meals and favorite toggles.
    single<MealQueueFlusher> { CombinedQueueFlusher(meals = get<PendingMealSync>(), favorites = get()) }
    // One instance for the whole app: a heart toggled on one screen is already filled on the others.
    single { FavoriteRecipesViewModel(repository = get()) }
    single {
        SignOut(
            authRepository = get<AuthRepository>(),
            mealPlanCache = get(),
            favorites = get(),
            pendingMeals = get(),
            pendingChanges = get(),
            orders = get(),
            addresses = get(),
        )
    }
}
