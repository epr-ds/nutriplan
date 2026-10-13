++ b/mobile/shared/src/commonTest/kotlin/com/nutriplan/shared/data/repository/AuthRepositoryTest.kt
package com.nutriplan.shared.data.repository

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class AuthRepositoryTest {

    private val repo = InMemoryAuthRepository()

    @Test
    fun `initial state has no tokens`() {
        assertNull(repo.currentAccessToken)
        assertNull(repo.currentRefreshToken)
        assertFalse(repo.isAuthenticated)
    }

    @Test
    fun `updateTokens sets tokens and marks authenticated`() {
        repo.updateTokens("access-token-123", "refresh-token-456")
        
        assertEquals("access-token-123", repo.currentAccessToken)
        assertEquals("refresh-token-456", repo.currentRefreshToken)
        assertTrue(repo.isAuthenticated)
    }

    @Test
    fun `clearTokens removes all tokens`() {
        repo.updateTokens("access-token-123", "refresh-token-456")
        assertTrue(repo.isAuthenticated)
        
        repo.clearTokens()
        
        assertNull(repo.currentAccessToken)
        assertNull(repo.currentRefreshToken)
        assertFalse(repo.isAuthenticated)
    }

    @Test
    fun `updateTokens with empty access token does not mark authenticated`() {
        repo.updateTokens("", "refresh-token-456")
        assertFalse(repo.isAuthenticated)
    }

    @Test
    fun `updateTokens overwrites previous tokens`() {
        repo.updateTokens("old-access", "old-refresh")
        repo.updateTokens("new-access", "new-refresh")
        
        assertEquals("new-access", repo.currentAccessToken)
        assertEquals("new-refresh", repo.currentRefreshToken)
    }

    @Test
    fun `isAuthenticated returns false when only refresh token exists`() {
        repo.updateTokens("", "refresh-token")
        assertFalse(repo.isAuthenticated)
    }

    @Test
    fun `isAuthenticated returns false when only access token exists`() {
        repo.updateTokens("access-token", "")
        assertFalse(repo.isAuthenticated)
    }

    @Test
    fun `clearTokens after multiple updates clears all`() {
        repo.updateTokens("access-1", "refresh-1")
        repo.updateTokens("access-2", "refresh-2")
        repo.clearTokens()
        
        assertNull(repo.currentAccessToken)
        assertNull(repo.currentRefreshToken)
        assertFalse(repo.isAuthenticated)
    }
}
