package com.nutriplan.android

import android.app.Application
import com.nutriplan.shared.data.local.DatabaseDriverFactory
import com.nutriplan.shared.data.local.SecureTokenStorage
import com.nutriplan.shared.data.local.TokenStorage
import com.nutriplan.shared.data.network.HttpClientProvider
import com.nutriplan.shared.data.repository.AuthRepository
import com.nutriplan.shared.di.KoinInitializer
import com.nutriplan.shared.di.cacheModule
import io.ktor.client.engine.okhttp.OkHttp
import org.koin.core.context.GlobalContext
import org.koin.dsl.module

/**
 * NutriPlan Android application entry point.
 *
 * Initializes Koin DI, the Ktor HTTP client, and Firebase Crashlytics for crash/ANR monitoring.
 */
class NutriPlanApplication : Application() {

    override fun onCreate() {
        super.onCreate()

        // HRD-602: Firebase Crashlytics auto-initializes via Gradle plugin (crash logging enabled by default in v19+).
        // Custom log messages can be added at key app events via FirebaseCrashlytics.getInstance().log("...")

        // Initialize Koin DI; the session is stored in the Android Keystore and meal plans are
        // cached on the device (cacheModule overrides the plain DietaryRepository).
        KoinInitializer.addModule(
            module { single<TokenStorage> { SecureTokenStorage(applicationContext) } },
            cacheModule(DatabaseDriverFactory(applicationContext)),
        )
        KoinInitializer.initialize()

        // Get AuthRepository from Koin and initialize Ktor HTTP client
        val authRepository = GlobalContext.get().get<AuthRepository>()
        HttpClientProvider.create(OkHttp, authRepository)
    }
}
