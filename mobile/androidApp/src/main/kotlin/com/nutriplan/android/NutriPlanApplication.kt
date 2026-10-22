package com.nutriplan.android

import android.app.Application
import com.nutriplan.android.analytics.FirebaseAnalyticsTracker
import com.nutriplan.android.auth.AndroidOAuthTokenProvider
import com.nutriplan.android.sync.WorkManagerSyncScheduler
import com.nutriplan.shared.auth.OAuthTokenProvider
import com.nutriplan.shared.data.ApiConfig
import com.nutriplan.shared.data.ApiEnvironment
import com.nutriplan.shared.data.local.DatabaseDriverFactory
import com.nutriplan.shared.data.local.SecureTokenStorage
import com.nutriplan.shared.data.local.TokenStorage
import com.nutriplan.shared.data.network.HttpClientProvider
import com.nutriplan.shared.data.repository.AuthRepository
import com.nutriplan.shared.data.repository.SyncScheduler
import com.nutriplan.shared.di.KoinInitializer
import com.nutriplan.shared.di.cacheModule
import com.nutriplan.shared.onboarding.DeviceOnboardingDraftStorage
import com.nutriplan.shared.onboarding.OnboardingDraftStorage
import io.ktor.client.engine.okhttp.OkHttp
import org.koin.core.context.GlobalContext
import org.koin.dsl.module

/**
 * NutriPlan Android application entry point.
 *
 * Initializes Koin DI, the Ktor HTTP client, Firebase Crashlytics for crash/ANR monitoring,
 * and Firebase Analytics for beta funnel/retention instrumentation (HRD-606).
 */
class NutriPlanApplication : Application() {

    /** Analytics tracker instance — initialized in [onCreate]. */
    val analyticsTracker: FirebaseAnalyticsTracker by lazy {
        FirebaseAnalyticsTracker(applicationContext).also(FirebaseAnalyticsTracker::initialize)
    }

    override fun onCreate() {
        super.onCreate()

        // IDN-402: point the data layer at the build's API environment before the HTTP client is
        // created (debug: dev, release: prod; overridable with -PapiEnv=local|stage).
        ApiConfig.configure(ApiEnvironment.fromName(BuildConfig.API_ENVIRONMENT))

        // HRD-602: Firebase Crashlytics auto-initializes via Gradle plugin (crash logging enabled by default in v19+).
        // Custom log messages can be added at key app events via FirebaseCrashlytics.getInstance().log("...")

        // Initialize Koin DI; the session is stored in the Android Keystore and meal plans are
        // cached on the device (cacheModule overrides the plain DietaryRepository).
        KoinInitializer.addModule(
            module {
                single<TokenStorage> { SecureTokenStorage(applicationContext) }
                single<OnboardingDraftStorage> { DeviceOnboardingDraftStorage(applicationContext) }
                // DPL-407: meals added offline are sent in the background once there is a network.
                single<SyncScheduler> { WorkManagerSyncScheduler(applicationContext) }
                // IDN-505: Google OAuth via Credential Manager (server client ID from the build).
                single<OAuthTokenProvider> {
                    AndroidOAuthTokenProvider(serverClientId = BuildConfig.GOOGLE_SERVER_CLIENT_ID)
                }
            },
            cacheModule(DatabaseDriverFactory(applicationContext)),
        )
        KoinInitializer.initialize()

        // Get AuthRepository from Koin and initialize Ktor HTTP client
        val authRepository = GlobalContext.get().get<AuthRepository>()
        HttpClientProvider.create(OkHttp, authRepository)

        // DPL-407: meals queued in an earlier run are sent as soon as the device is online. This only
        // schedules a background job (which does nothing when the queue is empty), so it never opens
        // the database during startup.
        GlobalContext.get().get<SyncScheduler>().requestSync()
    }
}
