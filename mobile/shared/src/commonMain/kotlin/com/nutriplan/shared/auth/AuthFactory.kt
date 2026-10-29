package com.nutriplan.shared.auth

import org.koin.mp.KoinPlatform

/**
 * App-facing factories for the auth screens (IDN-502 / IDN-504 / IDN-506).
 *
 * The Compose screens get their view models from Koin (see `sessionModule`); the iOS app, which has
 * no Koin lookup from Swift, gets them from here. Both point at the same default dependencies, so
 * behaviour is shared across platforms by construction.
 */
fun createLoginViewModel(): LoginViewModel = KoinPlatform.getKoin().get<LoginViewModel>()

fun createRegisterViewModel(): RegisterViewModel = KoinPlatform.getKoin().get<RegisterViewModel>()