package com.nutriplan.android

import android.app.Application
import com.nutriplan.shared.data.network.HttpClientProvider
import com.nutriplan.shared.di.KoinInitializer
import io.ktor.client.engine.okhttp.OkHttp

/**
 * NutriPlan Android application entry point.
 *
 * Initializes Koin DI and the Ktor HTTP client with the OkHttp engine.
 */
class NutriPlanApplication : Application() {

    override fun onCreate() {
        super.onCreate()

        // Initialize Koin DI
        KoinInitializer.initialize()

        // Initialize Ktor HTTP client with OkHttp engine
        HttpClientProvider.create(OkHttp)
    }
}
