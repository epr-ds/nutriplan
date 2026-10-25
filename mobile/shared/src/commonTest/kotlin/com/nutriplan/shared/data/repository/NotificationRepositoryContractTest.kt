package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.data.network.ApiFailure
import com.nutriplan.shared.data.network.HttpClientProvider
import com.nutriplan.shared.data.network.toApiFailure
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.HttpRequestData
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.TextContent
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

/**
 * [NotificationRepositoryImpl] against `contracts/notification.openapi.yaml` (NTF-601): the
 * device, feed and preferences calls the client makes, how it reads contract-shaped responses,
 * and how failures are classified. A [MockEngine] stands in for the notification service.
 */
class NotificationRepositoryContractTest {

    private val jsonHeaders = headersOf(HttpHeaders.ContentType, "application/json")

    private var lastRequest: HttpRequestData? = null

    @AfterTest
    fun tearDown() = HttpClientProvider.reset()

    private fun serve(status: HttpStatusCode = HttpStatusCode.OK, body: String = "{}"): NotificationRepositoryImpl {
        HttpClientProvider.create(
            MockEngine { request ->
                lastRequest = request
                respond(
                    content = body,
                    status = status,
                    headers = if (status.value < 400) jsonHeaders else headersOf(HttpHeaders.ContentType, "application/problem+json"),
                )
            },
            authRepository = null,
        )
        return NotificationRepositoryImpl()
    }

    private fun requestBody(): String = (lastRequest!!.body as TextContent).text

    @Test
    fun `register posts the platform and token and reads the registered device`() = runTest {
        val repository = serve(
            status = HttpStatusCode.Created,
            body = """{"id":"3f9d0f4e-1c2b-4d3e-9f8a-7b6c5d4e3f2a","platform":"ios","createdAt":"2026-10-24T00:00:00Z","updatedAt":"2026-10-24T00:00:00Z"}""",
        )

        val device = repository.registerDevice(platform = "ios", token = "fcm-token-1")

        assertEquals(HttpMethod.Post, lastRequest!!.method)
        assertEquals("/notifications/v1/notifications/devices", lastRequest!!.url.encodedPath)
        assertEquals("""{"platform":"ios","token":"fcm-token-1"}""", requestBody())
        assertEquals("3f9d0f4e-1c2b-4d3e-9f8a-7b6c5d4e3f2a", device.id)
    }

    @Test
    fun `revoke deletes the device registration`() = runTest {
        val repository = serve(status = HttpStatusCode.NoContent)

        repository.revokeDevice(deviceId = "device-1")

        assertEquals(HttpMethod.Delete, lastRequest!!.method)
        assertEquals("/notifications/v1/notifications/devices/device-1", lastRequest!!.url.encodedPath)
    }

    @Test
    fun `every documented failure is classified by status`() = runTest {
        val expected = mapOf(
            HttpStatusCode.Unauthorized to ApiFailure.SESSION_EXPIRED,
            HttpStatusCode.NotFound to ApiFailure.NOT_FOUND,
            HttpStatusCode.UnprocessableEntity to ApiFailure.REJECTED,
        )

        expected.forEach { (status, failure) ->
            val repository = serve(status = status, body = """{"type":"about:blank","title":"x","status":${status.value}}""")
            val error = assertFailsWith<ApiException> { repository.registerDevice(platform = "ios", token = "fcm-token-1") }
            assertEquals(failure, error.toApiFailure(), "status ${status.value}")
        }
    }
}