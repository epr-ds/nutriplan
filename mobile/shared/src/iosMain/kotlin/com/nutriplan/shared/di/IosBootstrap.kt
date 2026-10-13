package com.nutriplan.shared.di

import com.nutriplan.shared.data.local.SecureTokenStorage
import com.nutriplan.shared.data.local.TokenStorage
import com.nutriplan.shared.data.network.HttpClientProvider
import com.nutriplan.shared.data.repository.AuthRepository
import io.ktor.client.engine.darwin.Darwin
import org.koin.core.context.GlobalContext
import org.koin.dsl.module

/**
 * Entry points called from `NutriPlanApp.swift`.
 *
 * (Not named `initKoin`/`initHttpClient`: Kotlin/Native exposes top-level functions starting with
 * `init` to Swift as `doInit...`.)
 */
fun bootstrapKoin() {
    KoinInitializer.addModule(
        module { single<TokenStorage> { SecureTokenStorage() } },
    )
    KoinInitializer.initialize()
}

/** Create the shared HTTP client with the Darwin engine; call after [bootstrapKoin]. */
fun bootstrapHttpClient() {
    HttpClientProvider.create(Darwin, GlobalContext.get().get<AuthRepository>())
}
