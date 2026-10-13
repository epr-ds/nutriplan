package com.nutriplan.shared.di

import org.koin.core.context.startKoin
import org.koin.core.module.Module

/**
 * Application-level Koin initializer.
 *
 * Call [initialize] once at app startup (e.g., in Application.onCreate or iOS App.init).
 */
object KoinInitializer {

    private val appModules = mutableListOf<Module>()

    /**
     * Register additional Koin modules.
     */
    fun addModule(vararg modules: Module) {
        appModules.addAll(modules)
    }

    /**
     * Initialize Koin with all registered modules.
     *
     * Call this once during app initialization.
     */
    fun initialize() {
        startKoin {
            modules(dataModule)
            modules(appModules)
        }
    }

    /**
     * Stop Koin (useful for testing).
     */
    fun shutdown() {
        org.koin.core.context.stopKoin()
    }
}
