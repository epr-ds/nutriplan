package com.nutriplan.shared.di

import com.nutriplan.shared.auth.LoginViewModel
import com.nutriplan.shared.auth.OAuthTokenProvider
import com.nutriplan.shared.auth.OAuthViewModel
import com.nutriplan.shared.auth.RegisterViewModel
import com.nutriplan.shared.data.repository.AuthRepository
import com.nutriplan.shared.data.repository.IdentityRepository
import com.nutriplan.shared.onboarding.OnboardingDraftStorage
import com.nutriplan.shared.onboarding.OnboardingViewModel
import com.nutriplan.shared.session.CompleteOnboarding
import com.nutriplan.shared.session.DefaultSessionManager
import com.nutriplan.shared.session.Login
import com.nutriplan.shared.session.Logout
import com.nutriplan.shared.session.OAuthLogin
import com.nutriplan.shared.session.Register
import com.nutriplan.shared.session.SessionManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import org.koin.dsl.module

/**
 * Koin module for the session layer: the [SessionManager] and the auth use cases.
 *
 * Register it after [dataModule] so the [SessionManager] can read the shared [AuthRepository].
 * The manager gets its own application-lived scope, which it uses to follow the global
 * [com.nutriplan.shared.session.SessionEvents.signedOut] signal.
 */
val sessionModule = module {
    single<SessionManager> {
        DefaultSessionManager(
            authRepository = get<AuthRepository>(),
            scope = CoroutineScope(SupervisorJob() + Dispatchers.Default),
        )
    }
    single { Login(authRepository = get(), sessionManager = get()) }
    single { Register(authRepository = get(), sessionManager = get()) }
    single { OAuthLogin(authRepository = get(), sessionManager = get()) }
    single { Logout(authRepository = get(), sessionManager = get()) }
    // A fresh login form per screen, driven by the shared Login use case.
    factory { LoginViewModel(login = get()) }
    // A fresh registration form per screen, driven by the shared Register use case.
    factory { RegisterViewModel(register = get()) }
    // A fresh OAuth flow per screen; the token provider is supplied by the app modules.
    factory { OAuthViewModel(oauthLogin = get(), tokenProvider = get<OAuthTokenProvider>()) }
    single {
        CompleteOnboarding(
            identityRepository = get<IdentityRepository>(),
            sessionManager = get(),
        )
    }
    // A fresh wizard per onboarding flow; the draft storage is provided by the app modules.
    factory {
        OnboardingViewModel(
            draftStorage = get<OnboardingDraftStorage>(),
            completeOnboarding = get(),
        )
    }
}
