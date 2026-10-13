package com.nutriplan.android

import android.app.Application
import com.nutriplan.shared.data.local.SecureTokenStorage
import com.nutriplan.shared.data.local.TokenStorage
import com.nutriplan.shared.data.network.HttpClientProvider
import com.nutriplan.shared.data.repository.AuthRepository
import com.nutriplan.shared.di.KoinInitializer
import io.ktor.client.engine.okhttp.OkHttp
import org.koin.core.context.GlobalContext
import org.koin.dsl.module

/**
 * NutriPlan Android application entry point.
 *
 * Initializes Koin DI and the Ktor HTTP client with the OkHttp engine.
 */
class NutriPlanApplication : Application() {

    override fun onCreate() {
        super.onCreate()

        // Initialize Koin DI; the session is stored in the Android Keystore.
        KoinInitializer.addModule(
            module { single<TokenStorage> { SecureTokenStorage(applicationContext) } },
        )
        KoinInitializer.initialize()

        // Get AuthRepository from Koin and initialize Ktor HTTP client
        val authRepository = GlobalContext.get().get<AuthRepository>()
        HttpClientProvider.create(OkHttp, authRepository)
    }
}
