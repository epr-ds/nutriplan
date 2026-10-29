package com.nutriplan.shared.e2e

import com.nutriplan.shared.data.local.InMemoryOnboardingDraftStorage
import com.nutriplan.shared.data.local.TokenStorage
import com.nutriplan.shared.data.local.StoredTokens
import com.nutriplan.shared.data.model.RegisterRequest
import com.nutriplan.shared.data.network.HttpClientProvider
import com.nutriplan.shared.data.repository.AuthRepository
import com.nutriplan.shared.data.repository.IdentityRepository
import com.nutriplan.shared.di.dataModule
import com.nutriplan.shared.di.sessionModule
import com.nutriplan.shared.onboarding.OnboardingAnswers
import com.nutriplan.shared.onboarding.OnboardingDraftStorage
import com.nutriplan.shared.onboarding.OnboardingViewModel
import com.nutriplan.shared.session.CompleteOnboarding
import com.nutriplan.shared.session.SessionManager
import com.nutriplan.shared.session.SessionState
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import org.koin.core.context.GlobalContext
import org.koin.core.context.startKoin
import org.koin.core.context.stopKoin
import org.koin.core.module.Module
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

/**
 * IDN-703: the auth journey through the shared layer — register, onboard, reach an authenticated
 * `GET /users/me` — on every platform the shared code runs on: this runs on the JVM in the Android
 * jobs and on the iOS simulator in the iOS job, through the same shared view-models the Compose and
 * SwiftUI screens use, against a mock Identity backend. The Android UI version of the journey is
 * `AuthJourneyE2ETest` in the app module.
 */
class AuthJourneyTest {

    private val requests: MutableList<String> = mutableListOf()

    private val jsonHeaders = headersOf(HttpHeaders.ContentType, "application/json")

    private val engine = MockEngine { request ->
        val path = request.url.encodedPath
        requests.add("${request.method.value} $path")
        when {
            path.endsWith("/auth/register") ->
                respond(
                    """{"accessToken":"a1","refreshToken":"r1","expiresIn":900,"user":{"id":"u1","email":"ana@example.com","name":"Ana","dietaryPreferences":null}}""",
                    HttpStatusCode.OK,
                    jsonHeaders,
                )
            path.endsWith("/users/me/dietary-preferences") ->
                respond("{}", HttpStatusCode.OK, jsonHeaders)
            path.endsWith("/users/me") && request.method == HttpMethod.Get ->
                respond(
                    """{"id":"u1","email":"ana@example.com","name":"Ana","dietaryPreferences":{"dietType":"omnivore"}}""",
                    HttpStatusCode.OK,
                    jsonHeaders,
                )
            else -> respond("{}", HttpStatusCode.NotFound, jsonHeaders)
        }
    }

    private lateinit var authRepository: AuthRepository
    private lateinit var sessionManager: SessionManager
    private lateinit var identityRepository: IdentityRepository
    private lateinit var wizard: OnboardingViewModel

    @BeforeTest
    fun setUp() {
        startKoin {
            modules(
                dataModule,
                sessionModule,
                Module {
                    single<TokenStorage> { InMemoryTokenStorage() }
                    single<OnboardingDraftStorage> { InMemoryOnboardingDraftStorage() }
                },
            )
        }
        authRepository = GlobalContext.get<AuthRepository>()
        sessionManager = GlobalContext.get<SessionManager>()
        identityRepository = GlobalContext.get<IdentityRepository>()
        HttpClientProvider.create(engine, authRepository)
    }

    @AfterTest
    fun tearDown() {
        HttpClientProvider.reset()
        stopKoin()
    }

    @Test
    fun sign_up_then_onboarding_reaches_an_authenticated_users_me() = runTest {
        val register = authRepository.register(RegisterRequest(email = "ana@example.com", password = "secret12", name = "Ana"))
        assertNotNull(register.user)

        sessionManager.onAuthenticated(register.user)
        assertTrue(sessionManager.state.value is SessionState.Onboarding)

        wizard = OnboardingViewModel(InMemoryOnboardingDraftStorage(), CompleteOnboarding(identityRepository, sessionManager))
        wizard.updateAnswers(OnboardingAnswers(dietType = "omnivore"))
        assertTrue(wizard.next(), "the second onboarding step should be reachable")
        assertTrue(wizard.next(), "the targets step should be reachable")
        assertTrue(wizard.finish(), "the wizard should finish")

        val state = sessionManager.state.value
        assertTrue(state is SessionState.SignedIn, "expected a signed-in session, saw $state")
        assertEquals("u1", (state as SessionState.SignedIn).user.id)
    }
}

/** In-memory [TokenStorage] so the journey does not touch the platform secure store. */
private class InMemoryTokenStorage : TokenStorage {
    private var tokens: StoredTokens? = null
    override fun load(): StoredTokens? = tokens
    override fun save(accessToken: String, refreshToken: String) {
        tokens = StoredTokens(accessToken, refreshToken)
    }
    override fun clear() {
        tokens = null
    }
}