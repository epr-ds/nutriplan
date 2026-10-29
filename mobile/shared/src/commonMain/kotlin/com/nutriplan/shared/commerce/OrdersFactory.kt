package com.nutriplan.shared.commerce

import org.koin.core.KoinPlatform

/**
 * App-facing factory for the user's order list (COM-701 / COM-702).
 *
 * The Compose screens get their view model from Koin (see `cacheModule`); the iOS app, which gets
 * its view models from here, gets it from the same registered dependencies, so behaviour is shared
 * across platforms by construction.
 */
fun createOrderListViewModel(): OrderListViewModel = KoinPlatform.getKoin().get<OrderListViewModel>()