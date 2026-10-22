package com.nutriplan.shared.di

import com.nutriplan.shared.data.ApiConfig
import com.nutriplan.shared.data.ApiEnvironment
import com.nutriplan.shared.data.network.HttpClientProvider
import com.nutriplan.shared.data.repository.AuthRepository
import com.nutriplan.shared.data.repository.CommerceRepository
import com.nutriplan.shared.data.repository.CommerceRepositoryImpl
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.HttpRequestData
import io.ktor.http.HttpHeaders
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import org.koin.core.Koin
import org.koin.dsl.koinApplication
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertSame

/**
 * COM-502: the Commerce client is DI-managed and reuses the app's networking. It is resolved from
 * the real [dataModule], and it talks to the active environment's gateway with the session's bearer
 * token, exactly as the app wires it at startup (environment first, then Koin, then the HTTP client
 * with the Koin [AuthRepository]).
 */
class CommerceClientWiringTest {

    private val requests = mutableListOf<HttpRequestData>()

    @AfterTest
    fun tearDown() {
        HttpClientProvider.reset()
        ApiConfig.reset()
    }

    /** Wire like the app does and return the Koin container, signed in with [accessToken]. */
    private fun startApp(environment: ApiEnvironment, accessToken: String = "access-1"): Koin {
        ApiConfig.configure(environment)
        val koin = koinApplication { modules(dataModule) }.koin
        val auth = koin.get<AuthRepository>().apply { updateTokens(accessToken, "refresh-1") }
        HttpClientProvider.create(
            MockEngine { request ->
                requests += request
                respond(content = "[]", headers = headersOf(HttpHeaders.ContentType, "application/json"))
            },
            authRepository = auth,
        )
        return koin
    }

    @Test
    fun `koin provides one commerce client for the whole app`() {
        val koin = startApp(ApiEnvironment.DEV)

        val client = koin.get<CommerceRepository>()

        assertIs<CommerceRepositoryImpl>(client)
        assertSame(client, koin.get<CommerceRepository>())
    }

    @Test
    fun `commerce calls go to the configured environment's gateway`() = runTest {
        ApiEnvironment.entries.forEach { environment ->
            requests.clear()
            val koin = startApp(environment)

            koin.get<CommerceRepository>().listPaymentMethods()

            val url = requests.single().url
            assertEquals("${environment.baseUrl}/commerce/v1/payment-methods", url.toString(), environment.name)
            HttpClientProvider.reset()
        }
    }

    @Test
    fun `commerce calls carry the session's bearer token`() = runTest {
        val koin = startApp(ApiEnvironment.STAGE, accessToken = "token-abc")

        koin.get<CommerceRepository>().groceryProviders()

        assertEquals("Bearer token-abc", requests.single().headers[HttpHeaders.Authorization])
    }
}
