package com.nutriplan.shared.data.network

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class HeaderRedactionTest {

    @Test
    fun `authorization is redacted`() {
        assertTrue(isSensitiveHeader("Authorization"))
    }

    @Test
    fun `redaction is case-insensitive and ignores surrounding whitespace`() {
        assertTrue(isSensitiveHeader("authorization"))
        assertTrue(isSensitiveHeader("AUTHORIZATION"))
        assertTrue(isSensitiveHeader("  Cookie "))
    }

    @Test
    fun `cookies and api keys are redacted`() {
        assertTrue(isSensitiveHeader("Cookie"))
        assertTrue(isSensitiveHeader("Set-Cookie"))
        assertTrue(isSensitiveHeader("X-Api-Key"))
        assertTrue(isSensitiveHeader("Proxy-Authorization"))
    }

    @Test
    fun `ordinary headers are not redacted`() {
        assertFalse(isSensitiveHeader("Content-Type"))
        assertFalse(isSensitiveHeader("Accept"))
        assertFalse(isSensitiveHeader("X-Request-ID"))
    }
}
