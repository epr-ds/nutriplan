package com.nutriplan.shared.di

import com.nutriplan.shared.notifications.NotificationsViewModel
import org.koin.dsl.module

/**
 * Koin module for the in-app notification list (NTF-506).
 *
 * View-models are `factory` definitions: each screen gets its own state holder.
 */
val notificationsModule = module {
    factory { NotificationsViewModel(repository = get()) }
}