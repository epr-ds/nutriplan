package com.nutriplan.shared.integration

import com.nutriplan.shared.data.ApiConfig
import com.nutriplan.shared.data.ApiEnvironment
import com.nutriplan.shared.data.repository.InMemoryAuthRepository
import com.nutriplan.shared.data.repository.NotificationRepositoryImpl
import com.nutriplan.shared.data.network.HttpClientProvider
import com.nutriplan.shared.notifications.NotificationsViewModel
import io.ktor.client.engine.okhttp.OkHttp
import kotlinx.coroutines.test.runTest
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * True client↔backend integration test (mobile): the real Ktor HTTP client (OkHttp engine) against
 * a real backend HTTP server ([StubBackendServer]) for the notification centre — the same client
 * code path the Compose/SwiftUI screens use, no `MockEngine` in between. Guards the page envelope
 * (`items` + `unreadCount`) and the read-status round trip against the wire contract.
 */
class NotificationsBackendIntegrationTest {

    private val server = StubBackendServer()
    private val authRepository = InMemoryAuthRepository()
    private lateinit var viewModel: NotificationsViewModel

    @BeforeTest
    fun setUp() {
        server.start()
        ApiConfig.configure(ApiEnvironment.LOCAL)
        ApiConfig.useBaseUrl(server.baseUrl)
        authRepository.updateTokens(STUB_TOKEN, "integration-test-refresh-token")
        HttpClientProvider.create(OkHttp, authRepository = authRepository)
        viewModel = NotificationsViewModel(NotificationRepositoryImpl())
    }

    @AfterTest
    fun tearDown() {
        HttpClientProvider.reset()
        ApiConfig.reset()
        server.stop()
    }

    @Test
    fun `the notification feed loads through a real backend http server`() = runTest {
        viewModel.load()

        val state = viewModel.state.value
        assertNull(state.error, "the feed should load without error: ${state.error}")
        assertEquals(1, state.notifications.size)
        assertEquals("Meal plan ready", state.notifications.single().title)
        assertEquals("Your meal plan is ready to view.", state.notifications.single().body)
        assertEquals(1, state.unreadCount)
        assertEquals(false, state.notifications.single().isRead)

        // The feed page and the badge are two real requests against the backend.
        val paths = server.received.map { it.path }
        assertEquals(listOf("/notifications/v1/notifications", "/notifications/v1/notifications/unread-count"), paths)
        assertEquals(listOf("Bearer $STUB_TOKEN", "Bearer $STUB_TOKEN"), server.received.map { it.authorization })
    }

    @Test
    fun `marking a notification read goes through the real backend http server`() = runTest {
        viewModel.load()
        assertEquals(1, viewModel.state.value.unreadCount)

        viewModel.markAsRead("notif-meal-plan-ready")

        val state = viewModel.state.value
        assertTrue(state.notifications.single().isRead)
        assertEquals(0, state.unreadCount)
        assertEquals("POST", server.received.last().method)
        assertEquals("/notifications/v1/notifications/notif-meal-plan-ready/read", server.received.last().path)
    }

    private companion object {
        const val STUB_TOKEN = "integration-test-token"
    }
}