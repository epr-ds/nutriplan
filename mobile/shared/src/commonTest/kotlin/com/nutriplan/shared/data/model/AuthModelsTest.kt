++ b/mobile/shared/src/commonTest/kotlin/com/nutriplan/shared/data/model/AuthModelsTest.kt
package com.nutriplan.shared.data.model

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull

class AuthModelsTest {

    @Test
    fun `LoginRequest creates correctly`() {
        val request = LoginRequest("user@example.com", "password123")
        assertEquals("user@example.com", request.email)
        assertEquals("password123", request.password)
    }

    @Test
    fun `RegisterRequest creates correctly`() {
        val request = RegisterRequest("John Doe", "john@example.com", "password123")
        assertEquals("John Doe", request.name)
        assertEquals("john@example.com", request.email)
        assertEquals("password123", request.password)
    }

    @Test
    fun `RefreshRequest creates correctly`() {
        val request = RefreshRequest("refresh-token-abc")
        assertEquals("refresh-token-abc", request.refreshToken)
    }

    @Test
    fun `AuthResponse creates correctly`() {
        val response = AuthResponse(
            accessToken = "access-token-xyz",
            refreshToken = "refresh-token-xyz",
            expiresIn = 3600,
            tokenType = "Bearer"
        )
        assertEquals("access-token-xyz", response.accessToken)
        assertEquals("refresh-token-xyz", response.refreshToken)
        assertEquals(3600, response.expiresIn)
        assertEquals("Bearer", response.tokenType)
    }
}
