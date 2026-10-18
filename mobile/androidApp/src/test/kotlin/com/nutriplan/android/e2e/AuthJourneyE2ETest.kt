package com.nutriplan.android.e2e

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.a11y.TestApplication
import com.nutriplan.android.di.koinInject
import com.nutriplan.android.screen.auth.RegisterScreen
import com.nutriplan.android.screen.auth.RegisterTags
import com.nutriplan.android.screen.onboarding.OnboardingWizardScreen
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.shared.data.ApiConfig
import com.nutriplan.shared.data.local.StoredTokens
import com.nutriplan.shared.data.local.TokenStorage
import com.nutriplan.shared.data.network.HttpClientProvider
import com.nutriplan.shared.data.repository.AuthRepository
import com.nutriplan.shared.di.dataModule
import com.nutriplan.shared.di.sessionModule
import com.nutriplan.shared.onboarding.OnboardingDraftStorage
import com.nutriplan.shared.session.SessionManager
import com.nutriplan.shared.session.SessionState
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import java.util.Collections
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.koin.core.context.GlobalContext
import org.koin.core.context.startKoin
import org.koin.core.context.stopKoin
import org.koin.dsl.module
import org.robolectric.annotation.Config

/**
 * IDN-703: headless auth-journey E2E (Android).
 *
 * Drives the real UI (register → onboarding wizard) through the real shared view-models and
 * repositories, against a mock Identity backend, and asserts the journey reaches an authenticated
 * `GET /users/me`. Runs on the JVM via Robolectric (no emulator), in the `android-e2e` CI job.
 *
 * The iOS half of the acceptance criteria is tracked by IDN-506; the failure artifact is the
 * uploaded JUnit report rather than a device video on this JVM harness.
 */
@RunWith(AndroidJUnit4::class)
@Config(sdk = [34], application = TestApplication::class)
class AuthJourneyE2ETest {

    @get:Rule
    val compose = createComposeRule()

    /** Paths (with method) the data layer actually hit, in order. */
    private val requests: MutableList<String> = Collections.synchronizedList(mutableListOf())

    private val jsonHeaders = headersOf(HttpHeaders.ContentType, "application/json")

    private val engine = MockEngine { request ->
        val path = request.url.encodedPath
        requests += "${request.method.value} $path"
        when {
            path.endsWith("/auth/register") ->
                respond(REGISTER_RESPONSE, HttpStatusCode.OK, jsonHeaders)

            path.endsWith("/users/me/dietary-preferences") ->
                respond("""{"dietType":"omnivore"}""", HttpStatusCode.OK, jsonHeaders)

            path.endsWith("/users/me") && request.method == HttpMethod.Get ->
                respond(PROFILE_RESPONSE, HttpStatusCode.OK, jsonHeaders)

            else -> respond("{}", HttpStatusCode.NotFound, jsonHeaders)
        }
    }

    @Before
    fun setUp() {
        startKoin {
            modules(
                dataModule,
                sessionModule,
                module {
                    single<TokenStorage> { InMemoryTokenStorage() }
                    single<OnboardingDraftStorage> { InMemoryDraftStorage() }
                },
            )
        }
        val authRepository = GlobalContext.get().get<AuthRepository>()
        HttpClientProvider.create(engine, authRepository)
    }

    @After
    fun tearDown() {
        HttpClientProvider.reset()
        stopKoin()
        ApiConfig.reset()
    }

    @Test
    fun sign_up_then_onboarding_reaches_an_authenticated_users_me() {
        compose.setContent {
            NutriPlanTheme { AppJourneyHost() }
        }

        // Register (IDN-503).
        compose.onNodeWithTag(RegisterTags.NAME).performTextInput("Ana")
        compose.onNodeWithTag(RegisterTags.EMAIL).performTextInput("ana@example.com")
        compose.onNodeWithTag(RegisterTags.PASSWORD).performTextInput("secret12")
        compose.onNodeWithTag(RegisterTags.CONFIRM_PASSWORD).performTextInput("secret12")
        compose.onNodeWithText("Register").performScrollTo().performClick()

        // A brand-new user lands in onboarding (IDN-601/507).
        compose.waitUntil(timeoutMillis = 10_000) {
            compose.onAllNodesWithText("Step 1 of 3").fetchSemanticsNodes().isNotEmpty()
        }

        // Skipping still finishes the wizard and saves the (empty) preferences (IDN-605).
        compose.onNodeWithText("Skip").performClick()

        // The session flips to signed-in and the host shows the authenticated marker.
        compose.waitUntil(timeoutMillis = 10_000) {
            compose.onAllNodesWithTag(SIGNED_IN_TAG).fetchSemanticsNodes().isNotEmpty()
        }

        assertTrue(
            "expected a register call, saw $requests",
            requests.any { it == "POST /identity/v1/auth/register" },
        )
        assertTrue(
            "expected a preferences save, saw $requests",
            requests.any { it == "PUT /identity/v1/users/me/dietary-preferences" },
        )
        assertTrue(
            "expected the authed profile fetch, saw $requests",
            requests.any { it == "GET /identity/v1/users/me" },
        )
    }

    companion object {
        private const val SIGNED_IN_TAG = "signed_in"

        private const val REGISTER_RESPONSE =
            """{"accessToken":"a1","refreshToken":"r1","expiresIn":900,""" +
                """"user":{"id":"u1","email":"ana@example.com","name":"Ana"}}"""

        private const val PROFILE_RESPONSE =
            """{"id":"u1","email":"ana@example.com","name":"Ana",""" +
                """"dietaryPreferences":{"dietType":"omnivore"}}"""
    }
}

/**
 * Mirrors the app's session gate (IDN-507): show the auth flow while signed out, the onboarding
 * wizard while onboarding is incomplete, and a marker once the session is fully signed in.
 */
@Composable
private fun AppJourneyHost() {
    val sessionManager = koinInject<SessionManager>()
    val session by sessionManager.state.collectAsState()

    when (session) {
        is SessionState.SignedOut -> RegisterScreen(onRegisterSuccess = {}, onNavigateToLogin = {})
        is SessionState.Onboarding -> OnboardingWizardScreen(onComplete = {})
        is SessionState.SignedIn ->
            Text(text = "SIGNED_IN", modifier = Modifier.testTag("signed_in"))
    }
}

/** In-memory [TokenStorage] so the E2E does not touch the Android Keystore. */
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

/** In-memory onboarding draft store so resuming does not need SharedPreferences. */
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
