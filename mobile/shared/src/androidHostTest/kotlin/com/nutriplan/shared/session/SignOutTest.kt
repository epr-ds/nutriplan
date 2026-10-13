package com.nutriplan.shared.session

import app.cash.sqldelight.driver.jdbc.sqlite.JdbcSqliteDriver
import com.nutriplan.db.NutriPlanDatabase
import com.nutriplan.shared.data.local.MealPlanCache
import com.nutriplan.shared.data.local.StoredTokens
import com.nutriplan.shared.data.local.TokenStorage
import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.model.PlanMeal
import com.nutriplan.shared.data.network.HttpClientProvider
import com.nutriplan.shared.data.repository.CachedDietaryRepository
import com.nutriplan.shared.data.repository.DietaryRepository
import com.nutriplan.shared.data.repository.InMemoryAuthRepository
import com.nutriplan.shared.di.cacheModuleFor
import com.nutriplan.shared.di.dataModule
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

    private fun newCache(): MealPlanCache {
        val driver = JdbcSqliteDriver(JdbcSqliteDriver.IN_MEMORY)
        NutriPlanDatabase.Schema.create(driver)
        return MealPlanCache(NutriPlanDatabase(driver))
    }

    private fun plan(id: String) = MealPlan(
        id = id,
        name = "Plan $id",
        userId = "user-1",
        startDate = "2026-10-01",
        endDate = "2026-10-07",
        meals = listOf(
            PlanMeal(
                id = "m-$id",
                planId = id,
                recipeId = "r",
                recipeName = "Recipe",
                mealType = "LUNCH",
                scheduledDate = "2026-10-02",
            ),
        ),
        status = "ACTIVE",
    )

    @Test
    fun `cache clear removes every plan and meal`() {
        cache.upsert(plan("p1"), synced = true)
        cache.upsert(plan("p2"), synced = false)

        cache.clear()

        assertEquals(emptyList(), cache.getPlans())
        assertNull(cache.getPlan("p1"))
        assertEquals(emptyList(), cache.getUnsyncedPlans())
    }

    @Test
    fun `sign out ends the session and wipes secure storage and cached data`() {
        val storage = RecordingStorage()
        val auth = InMemoryAuthRepository(storage)
        auth.updateTokens("access", "refresh")
        cache.upsert(plan("p1"), synced = true)

        SignOut(auth, cache)()

        assertFalse(auth.isAuthenticated)
        assertNull(storage.stored)
        assertEquals(emptyList(), cache.getPlans())
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
