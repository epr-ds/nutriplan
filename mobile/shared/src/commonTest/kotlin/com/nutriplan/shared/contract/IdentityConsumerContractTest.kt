package com.nutriplan.shared.contract

import com.nutriplan.shared.data.model.AvatarUploadUrlRequest
import com.nutriplan.shared.data.model.LoginRequest
import com.nutriplan.shared.data.model.RefreshRequest
import com.nutriplan.shared.data.model.RegisterRequest
import com.nutriplan.shared.data.model.UpdateDietaryPreferencesRequest
import com.nutriplan.shared.data.model.UpdateProfileRequest
import com.nutriplan.shared.data.network.HttpClientProvider
import com.nutriplan.shared.data.repository.IdentityRepository
import com.nutriplan.shared.data.repository.IdentityRepositoryImpl
import com.nutriplan.shared.data.repository.InMemoryAuthRepository
import io.ktor.client.request.get
import io.ktor.http.HttpStatusCode
import kotlinx.coroutines.test.runTest
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Consumer contract tests for the KMP Identity client (IDN-702).
 *
 * The real repositories are pointed at [SpecDerivedIdentityMock]; every call must hit a
 * documented operation with a schema-shaped body, and the client must deserialize the
 * spec-shaped reply. A drifted client (renamed field, wrong path, changed type) makes a call
 * fail or gets flagged as a contract violation, which fails CI.
 */
class IdentityConsumerContractTest {

    private val mock = SpecDerivedIdentityMock()
    private lateinit var identity: IdentityRepository
    private lateinit var auth: InMemoryAuthRepository

    @BeforeTest
    fun setUp() {
        HttpClientProvider.create(mock.engine, authRepository = null)
        identity = IdentityRepositoryImpl()
        auth = InMemoryAuthRepository()
    }

    @AfterTest
    fun tearDown() = HttpClientProvider.reset()

    private fun assertNoViolations() =
        assertTrue(mock.violations.isEmpty(), () -> "contract violations: ${mock.violations}")

    @Test
    fun `register posts a documented request and reads the signed-in user`() = runTest {
        val response = auth.register(RegisterRequest("ana@example.com", "supersecret", "Ana Rivera"))

        assertEquals("Ana Rivera", response.user.name)
        assertEquals("access-token", response.accessToken)
        assertNoViolations()
    }

    @Test
    fun `login conforms to the contract`() = runTest {
        val response = auth.login(LoginRequest("ana@example.com", "supersecret"))

        assertEquals("ana@example.com", response.user.email)
        assertNoViolations()
    }

    @Test
    fun `refresh conforms to the contract`() = runTest {
        val response = auth.refreshToken("refresh-token")

        assertEquals("access-token", response.accessToken)
        assertNoViolations()
    }

    @Test
    fun `getMe deserializes the profile response`() = runTest {
        val profile = identity.getMe()

        assertEquals("Ana Rivera", profile.name)
        assertEquals("ana@example.com", profile.email)
        assertNoViolations()
    }

    @Test
    fun `updateMe sends a documented profile body`() = runTest {
        val profile = identity.updateMe(UpdateProfileRequest(name = "Ana R."))

        assertEquals("Ana Rivera", profile.name)
        assertNoViolations()
    }

    @Test
    fun `updateDietaryPreferences sends a documented preferences body`() = runTest {
        identity.updateDietaryPreferences(
            UpdateDietaryPreferencesRequest(
                dietType = "vegan",
                cuisinePreferences = listOf("mexican"),
                dailyCalorieTarget = 1800,
            ),
        )

        assertNoViolations()
    }

    @Test
    fun `requesting an avatar upload URL conforms to the contract`() = runTest {
        val response = identity.getAvatarUploadUrl(AvatarUploadUrlRequest("image/png"))

        assertEquals("avatars/user/abc.png", response.key)
        assertEquals("https://storage.example/upload", response.uploadUrl)
        assertNoViolations()
    }

    @Test
    fun `confirming an avatar sends the object key`() = runTest {
        identity.setAvatar("avatars/user/abc.png")

        assertNoViolations()
    }

    @Test
    fun `the mock rejects an operation the contract does not describe`() = runTest {
        val response = HttpClientProvider.client.get("${IdentityContract.clientPrefix}/auth/jwks")

        assertEquals(HttpStatusCode.BadRequest, response.status)
        assertTrue(mock.violations.any { it.contains("undocumented operation") })
    }
}
