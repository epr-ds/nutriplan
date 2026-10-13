package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.local.StoredTokens
import com.nutriplan.shared.data.local.TokenStorage
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class AuthRepositoryPersistenceTest {

    private class FakeTokenStorage(var stored: StoredTokens? = null) : TokenStorage {
        var loadFails = false
        var saveFails = false
        var clearFails = false

        override fun load(): StoredTokens? {
            if (loadFails) error("keystore unavailable")
            return stored
        }

        override fun save(accessToken: String, refreshToken: String) {
            if (saveFails) error("keystore unavailable")
            stored = StoredTokens(accessToken, refreshToken)
        }

        override fun clear() {
            if (clearFails) error("keystore unavailable")
            stored = null
        }
    }

    @Test
    fun `session is restored from storage on creation`() {
        val storage = FakeTokenStorage(StoredTokens("access", "refresh"))

        val repo = InMemoryAuthRepository(storage)

        assertTrue(repo.isAuthenticated)
        assertEquals("access", repo.currentAccessToken)
        assertEquals("refresh", repo.currentRefreshToken)
    }

    @Test
    fun `empty storage means logged out`() {
        val repo = InMemoryAuthRepository(FakeTokenStorage())

        assertFalse(repo.isAuthenticated)
        assertNull(repo.currentAccessToken)
    }

    @Test
    fun `updateTokens writes through to storage`() {
        val storage = FakeTokenStorage()
        val repo = InMemoryAuthRepository(storage)

        repo.updateTokens("a1", "r1")

        assertEquals(StoredTokens("a1", "r1"), storage.stored)
    }

    @Test
    fun `clearTokens clears storage`() {
        val storage = FakeTokenStorage(StoredTokens("a", "r"))
        val repo = InMemoryAuthRepository(storage)

        repo.clearTokens()

        assertNull(storage.stored)
        assertFalse(repo.isAuthenticated)
    }

    @Test
    fun `a new repository sees the session saved by the previous one`() {
        val storage = FakeTokenStorage()
        InMemoryAuthRepository(storage).updateTokens("a2", "r2")

        val next = InMemoryAuthRepository(storage)

        assertTrue(next.isAuthenticated)
        assertEquals("r2", next.currentRefreshToken)
    }

    @Test
    fun `unreadable storage does not crash startup`() {
        val storage = FakeTokenStorage(StoredTokens("a", "r")).apply { loadFails = true }

        val repo = InMemoryAuthRepository(storage)

        assertFalse(repo.isAuthenticated)
    }

    @Test
    fun `failing storage does not break the in-memory session`() {
        val storage = FakeTokenStorage().apply {
            saveFails = true
            clearFails = true
        }
        val repo = InMemoryAuthRepository(storage)

        repo.updateTokens("a", "r")
        assertTrue(repo.isAuthenticated)

        repo.clearTokens()
        assertFalse(repo.isAuthenticated)
    }
}
