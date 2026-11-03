package com.nutriplan.shared.integration

import com.nutriplan.shared.ai.AiAdvisor
import com.nutriplan.shared.ai.AiError
import com.nutriplan.shared.ai.AiRecommendationsViewModel
import com.nutriplan.shared.ai.AiResult
import com.nutriplan.shared.data.ApiConfig
import com.nutriplan.shared.data.ApiEnvironment
import com.nutriplan.shared.data.model.AiRecommendations
import com.nutriplan.shared.data.model.DietaryPreferences
import com.nutriplan.shared.data.repository.AiRepositoryImpl
import com.nutriplan.shared.data.repository.InMemoryAuthRepository
import com.nutriplan.shared.data.network.HttpClientProvider
import com.nutriplan.shared.session.SessionEvents
import io.ktor.client.engine.okhttp.OkHttp
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runTest
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertTrue

/**
 * True client↔backend integration test (mobile): the real Ktor HTTP client (OkHttp engine) against
 * a real backend HTTP server ([StubBackendServer]) for the AI advisor — the same client code path a
 * device takes (`AiRepositoryImpl` → `AiAdvisor` → screen ViewModel), no `MockEngine` in between.
 *
 * Covers the flow the AI Tips view runs: `POST /ai/v1/recommendations` answered with the contract's
 * recommendation envelope, and the failure mapping when the session is rejected.
 */
class AiBackendIntegrationTest {

    private val server = StubBackendServer()
    private val authRepository = InMemoryAuthRepository()
    private lateinit var advisor: AiAdvisor

    @BeforeTest
    fun setUp() {
        server.start()
        ApiConfig.configure(ApiEnvironment.LOCAL)
        ApiConfig.useBaseUrl(server.baseUrl)
        authRepository.updateTokens(STUB_TOKEN, "integration-test-refresh-token")
        HttpClientProvider.create(OkHttp, authRepository = authRepository)
        advisor = AiAdvisor(AiRepositoryImpl(authRepository = authRepository))
    }

    @AfterTest
    fun tearDown() {
        HttpClientProvider.reset()
        ApiConfig.reset()
        server.stop()
    }

    @Test
    fun `the ai advisor gets recommendations from a real backend http server`() = runTest {
        val outcome = advisor.recommend(preferences = DIETARY_PREFERENCES, mealType = "dinner")

        val value = (outcome as AiResult.Success<AiRecommendations>).value
        assertEquals(1, value.recommendations.size, "one recipe is recommended for the meal type")
        assertEquals("Lentil Curry", value.recommendations.single().name)
        assertEquals("A vegan dinner that fits a 2000 kcal target.", value.reasoning)
        assertEquals("This is not medical advice.", value.disclaimer)

        val request = server.received.single()
        assertEquals("POST", request.method)
        assertEquals("/ai/v1/recommendations", request.path)
        assertEquals("Bearer $STUB_TOKEN", request.authorization)
        assertTrue(request.body.contains("\"context\":\"single_meal\""), "unexpected ai body: ${request.body}")
        assertTrue(request.body.contains("\"mealType\":\"dinner\""), "unexpected ai body: ${request.body}")
    }

    @Test
    fun `the ai advisor retries with a refreshed token after a session expiry`() = runTest {
        authRepository.updateTokens(STUB_TOKEN, STUB_REFRESH_TOKEN)
        server.failNextFor(path = "/ai/v1/recommendations", status = 401, body = SESSION_EXPIRED_RESPONSE)

        val outcome = advisor.recommend(preferences = DIETARY_PREFERENCES, mealType = "dinner")

        val value = (outcome as AiResult.Success<AiRecommendations>).value
        assertEquals("Lentil Curry", value.recommendations.single().name)

        val aiCalls = server.received.filter { it.path == "/ai/v1/recommendations" }
        assertEquals(2, aiCalls.size, "the ai call should be retried once after the token refresh")
        assertEquals("Bearer $STUB_TOKEN", aiCalls[0].authorization)
        assertEquals("Bearer rotated-access-token-1", aiCalls[1].authorization)
    }

    @Test
    fun `the ai advisor reports a session expired error when the refresh token is rejected`() = runTest {
        authRepository.updateTokens(STUB_TOKEN, STUB_REFRESH_TOKEN)
        server.failNextFor(path = "/ai/v1/recommendations", status = 401, body = SESSION_EXPIRED_RESPONSE)
        server.failNextFor(path = "/identity/v1/auth/refresh", status = 401, body = SESSION_EXPIRED_RESPONSE)

        val signedOut = CompletableDeferred<Unit>()
        val collector = launch { SessionEvents.signedOut.collect { signedOut.complete(Unit) } }

        val outcome = advisor.recommend(preferences = DIETARY_PREFERENCES, mealType = "dinner")

        val error = assertIs<AiResult.Failure>(outcome).error
        assertEquals(AiError.SESSION_EXPIRED, error)
        assertFalse(authRepository.isAuthenticated)
        // The failed refresh must have emitted the signed-out signal; await it.
        signedOut.await()
        collector.cancel()
    }

    private companion object {
        const val STUB_TOKEN = "integration-test-token"
        const val STUB_REFRESH_TOKEN = "integration-test-refresh-token"

        val DIETARY_PREFERENCES = DietaryPreferences(
            dietType = "vegan",
            allergies = listOf("Peanuts"),
            dailyCalorieTarget = 2000,
        )

        val SESSION_EXPIRED_RESPONSE = """
            { "title": "Unauthorized", "status": 401, "detail": "The session expired or was revoked." }
        """.trimIndent()
    }
}
