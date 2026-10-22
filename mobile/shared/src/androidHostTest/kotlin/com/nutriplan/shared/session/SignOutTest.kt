package com.nutriplan.shared.session

import app.cash.sqldelight.driver.jdbc.sqlite.JdbcSqliteDriver
import com.nutriplan.db.NutriPlanDatabase
import com.nutriplan.shared.data.local.MealPlanCache
import com.nutriplan.shared.data.local.StoredTokens
import com.nutriplan.shared.data.local.TokenStorage
import com.nutriplan.shared.data.network.HttpClientProvider
import com.nutriplan.shared.data.repository.CachedDietaryRepository
import com.nutriplan.shared.data.repository.DietaryRepository
import com.nutriplan.shared.data.repository.InMemoryAuthRepository
import com.nutriplan.shared.di.cacheModuleFor
import com.nutriplan.shared.data.repository.FavoriteRecipesRepository
import com.nutriplan.shared.di.dataModule
import com.nutriplan.shared.recipes.FavoriteRecipesViewModel
import com.nutriplan.shared.data.local.PendingMealStore
import com.nutriplan.shared.testing.FakeFavoriteRemote
import com.nutriplan.shared.testing.addRequest
import com.nutriplan.shared.testing.newDatabase
import com.nutriplan.shared.testing.favoriteRecipe
import com.nutriplan.shared.testing.newFavoriteCache
import com.nutriplan.shared.testing.fullPlan
import com.nutriplan.shared.testing.meal
import com.nutriplan.shared.testing.newCache
import com.nutriplan.shared.testing.summary
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import org.koin.dsl.koinApplication
import org.koin.dsl.module
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class SignOutTest {

    private class RecordingStorage(var stored: StoredTokens? = null) : TokenStorage {
        override fun load(): StoredTokens? = stored
        override fun save(accessToken: String, refreshToken: String) {
            stored = StoredTokens(accessToken, refreshToken)
        }
        override fun clear() {
            stored = null
        }
    }

    private lateinit var cache: MealPlanCache

    @BeforeTest
    fun setUp() {
        cache = newCache()
        HttpClientProvider.create(MockEngine { respond("{}") }, authRepository = null)
    }

    @AfterTest
    fun tearDown() = HttpClientProvider.reset()

    @Test
    fun `sign out ends the session and wipes secure storage and cached data`() {
        val storage = RecordingStorage()
        val auth = InMemoryAuthRepository(storage)
        auth.updateTokens("access", "refresh")
        cache.upsertPlan(fullPlan("p1", meals = listOf(meal("m1"))))
        cache.upsertSummaries(listOf(summary("p2")))
        val favoriteCache = newFavoriteCache().apply { replaceAll(listOf(favoriteRecipe("f1"))) }
        val favorites = FavoriteRecipesViewModel(FavoriteRecipesRepository(FakeFavoriteRemote(), favoriteCache))

        val queue = PendingMealStore(newDatabase())
        queue.enqueue("p1", addRequest(), null, com.nutriplan.shared.data.model.PlanMealRecipe(id = "r1", name = "Soup"), null)

        val changes = com.nutriplan.shared.data.local.PendingChangeStore(newDatabase())
        changes.queueRemove("p1", com.nutriplan.shared.testing.meal("m1"))

        SignOut(auth, cache, favorites, queue, changes)()

        assertFalse(auth.isAuthenticated)
        assertNull(storage.stored)
        assertEquals(emptyList(), cache.getPlans())
        assertNull(cache.getPlan("p1"))
        assertEquals(emptyList(), favoriteCache.getAll(), "favorites are wiped too")
        assertEquals(emptyList(), favorites.state.value.recipes)
        assertTrue(queue.waiting().isEmpty(), "meals waiting to be sent belong to the signed-out user")
        assertTrue(changes.waiting().isEmpty(), "so do edits and removals")
    }

    @Test
    fun `cacheModule replaces the dietary repository and provides sign out`() {
        val storage = RecordingStorage(StoredTokens("a", "r"))
        val koin = koinApplication {
            modules(
                dataModule,
                module { single<TokenStorage> { storage } },
                cacheModuleFor { JdbcSqliteDriver(JdbcSqliteDriver.IN_MEMORY).also { NutriPlanDatabase.Schema.create(it) } },
            )
        }.koin

        assertTrue(koin.get<DietaryRepository>() is CachedDietaryRepository)

        koin.get<SignOut>()()

        assertNull(storage.stored)
    }
}
