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
            firstName = "John",
            lastName = "Doe",
        )
        assertEquals("john@example.com", request.email)
        assertEquals("password123", request.password)
        assertEquals("John", request.firstName)
        assertEquals("Doe", request.lastName)
        assertNull(request.dietaryPreferences)
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
            expiresIn = 3600L,
        )
        assertEquals("access-token-xyz", response.accessToken)
        assertEquals("refresh-token-xyz", response.refreshToken)
        assertEquals(3600L, response.expiresIn)
    }

    @Test
    fun `UserProfile optional fields default to null`() {
        val profile = UserProfile(
            id = "user-1",
            email = "john@example.com",
            firstName = "John",
            lastName = "Doe",
        )
        assertEquals("user-1", profile.id)
        assertNull(profile.avatarUrl)
        assertNull(profile.dietaryPreferences)
    }
}