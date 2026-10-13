package com.nutriplan.shared.di

import com.nutriplan.shared.data.repository.AiRepository
import com.nutriplan.shared.data.repository.AiRepositoryImpl
import com.nutriplan.shared.data.repository.AuthRepository
import com.nutriplan.shared.data.repository.CommerceRepository
import com.nutriplan.shared.data.repository.CommerceRepositoryImpl
import com.nutriplan.shared.data.repository.DietaryRepository
import com.nutriplan.shared.data.repository.DietaryRepositoryImpl
import com.nutriplan.shared.data.repository.IdentityRepository
import com.nutriplan.shared.data.repository.IdentityRepositoryImpl
import com.nutriplan.shared.data.repository.NotificationRepository
import com.nutriplan.shared.data.repository.NotificationRepositoryImpl
import com.nutriplan.shared.data.repository.InMemoryAuthRepository
import com.nutriplan.shared.data.local.TokenStorage
import org.koin.dsl.module

/**
 * Koin module providing all data-layer repositories.
 *
 * Repositories are singletons scoped to the application lifecycle.
 */
val dataModule = module {
    // Auth repository: restores and persists the session through the platform TokenStorage
    // (registered by the app; without one the session lives in memory only).
    single<AuthRepository> { InMemoryAuthRepository(tokenStorage = getOrNull<TokenStorage>()) }

    // API repositories
    single<IdentityRepository> { IdentityRepositoryImpl() }
    single<DietaryRepository> { DietaryRepositoryImpl() }
    single<AiRepository> { AiRepositoryImpl() }
    single<CommerceRepository> { CommerceRepositoryImpl() }
    single<NotificationRepository> { NotificationRepositoryImpl() }
}
