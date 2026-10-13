package com.nutriplan.shared.data

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

class ApiConfigTest {

    @Test
    fun `BASE_URL is correctly configured`() {
        assertEquals("https://api.nutriplan.app", ApiConfig.BASE_URL)
    }

    @Test
    fun `IDENTITY endpoint is correctly configured`() {
        assertEquals("https://api.nutriplan.app/identity/v1", ApiConfig.IDENTITY)
    }

    @Test
    fun `DIETARY endpoint is correctly configured`() {
        assertEquals("https://api.nutriplan.app/dietary/v1", ApiConfig.DIETARY)
    }

    @Test
    fun `AI endpoint is correctly configured`() {
        assertEquals("https://api.nutriplan.app/ai/v1", ApiConfig.AI)
    }

    @Test
    fun `COMMERCE endpoint is correctly configured`() {
        assertEquals("https://api.nutriplan.app/commerce/v1", ApiConfig.COMMERCE)
    }

    @Test
    fun `NOTIFICATION endpoint is correctly configured`() {
        assertEquals("https://api.nutriplan.app/notification/v1", ApiConfig.NOTIFICATION)
    }

    @Test
    fun `all endpoints are non-empty`() {
        assertNotNull(ApiConfig.BASE_URL)
        assertNotNull(ApiConfig.IDENTITY)
        assertNotNull(ApiConfig.DIETARY)
        assertNotNull(ApiConfig.AI)
        assertNotNull(ApiConfig.COMMERCE)
        assertNotNull(ApiConfig.NOTIFICATION)
    }

    @Test
    fun `all endpoints start with https`() {
        assertTrue(ApiConfig.BASE_URL.startsWith("https://"))
        assertTrue(ApiConfig.IDENTITY.startsWith("https://"))
        assertTrue(ApiConfig.DIETARY.startsWith("https://"))
        assertTrue(ApiConfig.AI.startsWith("https://"))
        assertTrue(ApiConfig.COMMERCE.startsWith("https://"))
        assertTrue(ApiConfig.NOTIFICATION.startsWith("https://"))
    }
}
