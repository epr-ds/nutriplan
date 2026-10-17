package com.nutriplan.shared.data.model

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class AuthModelsTest {

    @Test
    fun `LoginRequest creates correctly`() {
        val request = LoginRequest("user@example.com", "password123")
        assertEquals("user@example.com", request.email)
        assertEquals("password123", request.password)
    }

    @Test
    fun `RegisterRequest creates correctly`() {
        val request = RegisterRequest(
            email = "john@example.com",
            password = "password123",
            name = "John Doe",
        )
        assertEquals("john@example.com", request.email)
        assertEquals("password123", request.password)
        assertEquals("John Doe", request.name)
    }

    @Test
    fun `RefreshRequest creates correctly`() {
        val request = RefreshRequest("refresh-token-abc")
        assertEquals("refresh-token-abc", request.refreshToken)
    }

    @Test
    fun `AuthResponse carries the returned user`() {
        val response = AuthResponse(
            accessToken = "access-token-xyz",
            refreshToken = "refresh-token-xyz",
            expiresIn = 3600L,
            user = UserProfile(id = "user-1", email = "john@example.com", name = "John Doe"),
        )
        assertEquals("access-token-xyz", response.accessToken)
        assertEquals("refresh-token-xyz", response.refreshToken)
        assertEquals(3600L, response.expiresIn)
        assertEquals("John Doe", response.user.name)
    }

    @Test
    fun `UserProfile optional fields default to null`() {
        val profile = UserProfile(
            id = "user-1",
            email = "john@example.com",
            name = "John Doe",
        )
        assertEquals("user-1", profile.id)
        assertNull(profile.avatarUrl)
        assertNull(profile.dietaryPreferences)
        assertNull(profile.createdAt)
    }
}
