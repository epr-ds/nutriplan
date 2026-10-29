package com.nutriplan.shared.e2e

import com.nutriplan.shared.data.local.StoredTokens
import com.nutriplan.shared.data.local.TokenStorage
import com.nutriplan.shared.data.model.RegisterRequest
import com.nutriplan.shared.data.network.HttpClientProvider
import com.nutriplan.shared.data.repository.AuthRepository
import com.nutriplan.shared.data.repository.InMemoryAuthRepository
import com.nutriplan.shared.data.repository.IdentityRepository
import com.nutriplan.shared.data.repository.IdentityRepositoryImpl
import com.nutriplan.shared.onboarding.OnboardingAnswers
import com.nutriplan.shared.onboarding.OnboardingDraftStorage
import com.nutriplan.shared.onboarding.OnboardingViewModel
import com.nutriplan.shared.session.CompleteOnboarding
import com.nutriplan.shared.session.DefaultSessionManager
import com.nutriplan.shared.session.SessionManager
import com.nutriplan.shared.session.SessionState
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.test.runTest
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
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

    @BeforeTest
    fun setUp() {
        val tokenStorage = InMemoryTokenStorage()
        authRepository = InMemoryAuthRepository(tokenStorage)
        val sessionScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
        sessionManager = DefaultSessionManager(authRepository, sessionScope)
        identityRepository = IdentityRepositoryImpl()
        HttpClientProvider.create(engine, authRepository)
    }

    @AfterTest
    fun tearDown() {
        HttpClientProvider.reset()
    }

    @Test
    fun sign_up_then_onboarding_reaches_an_authenticated_users_me() = runTest {
        val register = authRepository.register(RegisterRequest(email = "ana@example.com", password = "secret12", name = "Ana"))
        assertNotNull(register.user)

        // A brand-new user (no dietary preferences yet) lands in onboarding.
        sessionManager.onAuthenticated(register.user)
        assertIs<SessionState.Onboarding>(sessionManager.state.value)

        val wizard = OnboardingViewModel(InMemoryDraftStorage(), CompleteOnboarding(identityRepository, sessionManager))
        wizard.updateAnswers(OnboardingAnswers(dietType = "omnivore"))
        assertTrue(wizard.next(), "the second onboarding step should be reachable")
        assertTrue(wizard.next(), "the targets step should be reachable")
        assertTrue(wizard.finish(), "the wizard should finish")

        // Finishing persisted the preferences and fetched the profile, so the session is signed in.
        val signedIn = assertIs<SessionState.SignedIn>(sessionManager.state.value)
        assertEquals("u1", signedIn.user.id)

        assertTrue(
            requests.any { it.startsWith("POST ") && it.endsWith("/auth/register") },
            "expected a register call, saw $requests",
        )
        assertTrue(
            requests.any { it.startsWith("PUT ") && it.endsWith("/users/me/dietary-preferences") },
            "expected a preferences save, saw $requests",
        )
        assertTrue(
            requests.any { it.startsWith("GET ") && it.endsWith("/users/me") },
            "expected the authed profile fetch, saw $requests",
        )
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

/** In-memory [OnboardingDraftStorage] so the wizard does not need the platform key-value store. */
private class InMemoryDraftStorage : OnboardingDraftStorage {
    private var draft: String? = null
    override fun loadDraft(): String? = draft
    override fun saveDraft(draft: String) {
        this.draft = draft
    }
    override fun clearDraft() {
        draft = null
    }
}