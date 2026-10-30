package com.nutriplan.shared.data

import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals

class ApiEnvironmentTest {

    @BeforeTest
    fun setUp() = ApiConfig.reset()

    @AfterTest
    fun tearDown() = ApiConfig.reset()

    @Test
    fun `production is the default environment`() {
        assertEquals(ApiEnvironment.PROD, ApiConfig.environment)
        assertEquals("https://api.nutriplan.app", ApiConfig.BASE_URL)
    }

    @Test
    fun `each environment derives every service URL from its own origin`() {
        ApiEnvironment.entries.forEach { environment ->
            ApiConfig.configure(environment)
            assertEquals(environment.baseUrl, ApiConfig.BASE_URL)
            assertEquals("${environment.baseUrl}/identity/v1", ApiConfig.IDENTITY)
            assertEquals("${environment.baseUrl}/dietary/v1", ApiConfig.DIETARY)
            assertEquals("${environment.baseUrl}/ai/v1", ApiConfig.AI)
            assertEquals("${environment.baseUrl}/commerce/v1", ApiConfig.COMMERCE)
            assertEquals("${environment.baseUrl}/notifications/v1", ApiConfig.NOTIFICATION)
        }
    }

    @Test
    fun `local environment points at the emulator loopback`() {
        ApiConfig.configure(ApiEnvironment.LOCAL)
        assertEquals("http://10.0.2.2:8080", ApiConfig.BASE_URL)
        assertEquals("http://10.0.2.2:8080/identity/v1", ApiConfig.IDENTITY)
    }

    @Test
    fun `fromName is case-insensitive and tolerates whitespace`() {
        assertEquals(ApiEnvironment.LOCAL, ApiEnvironment.fromName("local"))
        assertEquals(ApiEnvironment.DEV, ApiEnvironment.fromName("DEV"))
        assertEquals(ApiEnvironment.STAGE, ApiEnvironment.fromName("  Stage "))
        assertEquals(ApiEnvironment.PROD, ApiEnvironment.fromName("prod"))
    }

    @Test
    fun `fromName falls back to prod for unknown or missing values`() {
        assertEquals(ApiEnvironment.PROD, ApiEnvironment.fromName("nope"))
        assertEquals(ApiEnvironment.PROD, ApiEnvironment.fromName(null))
        assertEquals(ApiEnvironment.PROD, ApiEnvironment.fromName(""))
    }
}
