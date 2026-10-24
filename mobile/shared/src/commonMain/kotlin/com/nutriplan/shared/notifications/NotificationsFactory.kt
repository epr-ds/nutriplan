package com.nutriplan.shared.notifications

import com.nutriplan.shared.data.repository.NotificationRepositoryImpl

/**
 * App-facing factory for the in-app notification view model (NTF-506 / NTF-507).
 *
 * The Compose screens get their view model from Koin (see `notificationsModule`); the iOS app,
 * which has no Koin lookup from Swift, gets it from here. Both point at the same default
 * repository, so behaviour is shared across platforms by construction.
 */
fun createNotificationsViewModel(): NotificationsViewModel = NotificationsViewModel(
    repository = NotificationRepositoryImpl(),
)