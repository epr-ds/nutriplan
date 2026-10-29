package com.nutriplan.shared.commerce

import org.koin.mp.KoinPlatform

/**
 * App-facing factories for the user's order screens (COM-701 / COM-702 / COM-704 / COM-606).
 *
 * The Compose screens get their view models from Koin (see `cacheModule`); the iOS app, which has no
 * Koin lookup from Swift, gets them from here. Both point at the same default dependencies, so
 * behaviour is shared across platforms by construction.
 */
fun createOrderListViewModel(): OrderListViewModel = KoinPlatform.getKoin().get<OrderListViewModel>()

fun createOrderDetailViewModel(): OrderDetailViewModel = KoinPlatform.getKoin().get<OrderDetailViewModel>()

fun createCheckoutViewModel(): CheckoutViewModel = KoinPlatform.getKoin().get<CheckoutViewModel>()