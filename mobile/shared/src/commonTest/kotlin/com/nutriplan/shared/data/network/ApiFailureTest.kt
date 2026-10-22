package com.nutriplan.shared.data.network

import kotlin.test.Test
import kotlin.test.assertEquals

class ApiFailureTest {

    @Test
    fun `http errors classify by status`() {
        val expected = mapOf(
            401 to ApiFailure.SESSION_EXPIRED,
            403 to ApiFailure.FORBIDDEN,
            404 to ApiFailure.NOT_FOUND,
            409 to ApiFailure.CONFLICT,
            400 to ApiFailure.REJECTED,
            422 to ApiFailure.REJECTED,
            500 to ApiFailure.SERVER,
            502 to ApiFailure.SERVER,
            599 to ApiFailure.SERVER,
            418 to ApiFailure.UNKNOWN,
            302 to ApiFailure.UNKNOWN,
        )

        expected.forEach { (status, failure) ->
            assertEquals(failure, ApiException.HttpError(status, null).toApiFailure(), "status $status")
        }
    }

    @Test
    fun `a real network error is offline`() {
        assertEquals(ApiFailure.OFFLINE, ApiException.NetworkError().toApiFailure())
    }

    @Test
    fun `the create helper's misnamed NetworkError is classified by its code not its class`() {
        // ApiException.create returns a NetworkError even for 401/403/404, so a 401 must not look offline.
        assertEquals(ApiFailure.SESSION_EXPIRED, ApiException.create("x", ApiException.Code.UNAUTHORIZED).toApiFailure())
        assertEquals(ApiFailure.FORBIDDEN, ApiException.create("x", ApiException.Code.FORBIDDEN).toApiFailure())
        assertEquals(ApiFailure.NOT_FOUND, ApiException.create("x", ApiException.Code.NOT_FOUND).toApiFailure())
        assertEquals(ApiFailure.CONFLICT, ApiException.create("x", ApiException.Code.CONFLICT).toApiFailure())
        assertEquals(ApiFailure.SERVER, ApiException.create("x", ApiException.Code.SERVER_ERROR).toApiFailure())
        assertEquals(ApiFailure.OFFLINE, ApiException.create("x", ApiException.Code.NETWORK_ERROR).toApiFailure())
    }

    @Test
    fun `other api exceptions and foreign errors are unknown`() {
        assertEquals(ApiFailure.UNKNOWN, ApiException.SerializationError().toApiFailure())
        assertEquals(ApiFailure.UNKNOWN, ApiException.Unknown().toApiFailure())
        assertEquals(ApiFailure.UNKNOWN, IllegalStateException("boom").toApiFailure())
    }
}
