package com.nutriplan.shared.data.network

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ApiExceptionTest {

    @Test
    fun `HttpError 400 maps to CONFLICT`() {
        val error = ApiException.HttpError(400, "Bad Request")
        assertEquals(ApiException.Code.CONFLICT, error.code)
        assertTrue(error.message.orEmpty().contains("400"))
    }

    @Test
    fun `HttpError 401 maps to UNAUTHORIZED`() {
        val error = ApiException.HttpError(401, "Unauthorized")
        assertEquals(ApiException.Code.UNAUTHORIZED, error.code)
    }

    @Test
    fun `HttpError 403 maps to FORBIDDEN`() {
        val error = ApiException.HttpError(403, "Forbidden")
        assertEquals(ApiException.Code.FORBIDDEN, error.code)
    }

    @Test
    fun `HttpError 404 maps to NOT_FOUND`() {
        val error = ApiException.HttpError(404, "Not Found")
        assertEquals(ApiException.Code.NOT_FOUND, error.code)
    }

    @Test
    fun `HttpError 500 maps to SERVER_ERROR`() {
        val error = ApiException.HttpError(500, "Internal Server Error")
        assertEquals(ApiException.Code.SERVER_ERROR, error.code)
    }

    @Test
    fun `HttpError 422 maps to HTTP_ERROR`() {
        val error = ApiException.HttpError(422, "Unprocessable Entity")
        assertEquals(ApiException.Code.HTTP_ERROR, error.code)
    }

    @Test
    fun `HttpError with null body shows Unknown error`() {
        val error = ApiException.HttpError(500, null)
        assertTrue(error.message.orEmpty().contains("Unknown error"))
    }

    @Test
    fun `NetworkError preserves cause`() {
        val cause = RuntimeException("Connection refused")
        val error = ApiException.NetworkError(cause)
        assertEquals(ApiException.Code.NETWORK_ERROR, error.code)
        assertEquals(cause, error.cause)
        assertEquals("Network error", error.message)
    }

    @Test
    fun `NetworkError with null cause shows Network error`() {
        val error = ApiException.NetworkError(null)
        assertEquals(ApiException.Code.NETWORK_ERROR, error.code)
        assertEquals("Network error", error.message)
    }

    @Test
    fun `SerializationError preserves cause`() {
        val cause = RuntimeException("Invalid JSON")
        val error = ApiException.SerializationError(cause)
        assertEquals(ApiException.Code.SERIALIZATION_ERROR, error.code)
        assertEquals(cause, error.cause)
    }

    @Test
    fun `SerializationError with null cause shows Serialization error`() {
        val error = ApiException.SerializationError(null)
        assertEquals(ApiException.Code.SERIALIZATION_ERROR, error.code)
        assertEquals("Serialization error", error.message)
    }

    @Test
    fun `Unknown error has correct code and message`() {
        val error = ApiException.Unknown()
        assertEquals(ApiException.Code.UNKNOWN, error.code)
        assertEquals("Unknown error", error.message)
    }

    @Test
    fun `all error codes are defined`() {
        val codes = ApiException.Code.values()
        assertEquals(9, codes.size)
        assertTrue(codes.contains(ApiException.Code.NETWORK_ERROR))
        assertTrue(codes.contains(ApiException.Code.HTTP_ERROR))
        assertTrue(codes.contains(ApiException.Code.UNAUTHORIZED))
        assertTrue(codes.contains(ApiException.Code.FORBIDDEN))
        assertTrue(codes.contains(ApiException.Code.NOT_FOUND))
        assertTrue(codes.contains(ApiException.Code.CONFLICT))
        assertTrue(codes.contains(ApiException.Code.SERVER_ERROR))
        assertTrue(codes.contains(ApiException.Code.SERIALIZATION_ERROR))
        assertTrue(codes.contains(ApiException.Code.UNKNOWN))
    }
}
