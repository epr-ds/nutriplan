package com.nutriplan.shared.onboarding

import org.koin.mp.KoinPlatform

/**
 * App-facing factory for the onboarding wizard (IDN-901).
 *
 * The Compose screens get their view model from Koin (see `SessionModule`); the iOS app, which has
 * no Koin lookup from Swift, gets it from here. Both point at the same default dependencies, so
 * behaviour is shared across platforms by construction.
 */
fun createOnboardingViewModel(): OnboardingViewModel = KoinPlatform.getKoin().get<OnboardingViewModel>()