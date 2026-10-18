package com.nutriplan.shared.auth

import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.session.DefaultSessionManager
import com.nutriplan.shared.session.FakeAuthRepository
import com.nutriplan.shared.session.Register
import com.nutriplan.shared.session.SessionState
import com.nutriplan.shared.session.authResponse
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

class RegisterViewModelTest {

    private class Fixture(
        val model: RegisterViewModel,
        val repository: FakeAuthRepository,
        val session: DefaultSessionManager,
    )

    private fun fixture(
        scope: CoroutineScope,
        error: Throwable? = null,
    ): Fixture {
        val repository = FakeAuthRepository(
            response = authResponse(onboardingComplete = false),
            error = error,
        )
        val session = DefaultSessionManager(FakeAuthRepository(), scope)
        return Fixture(RegisterViewModel(Register(repository, session)), repository, session)
    }

    private fun RegisterViewModel.fillValidForm() {
        onNameChange("Ana")
        onEmailChange("ana@example.com")
        onPasswordChange("secret-password")
        onConfirmPasswordChange("secret-password")
    }

    @Test
    fun `blank fields are rejected with inline errors before any request`() = runTest {
        val fx = fixture(backgroundScope)

        assertFalse(fx.model.submit())

        val state = fx.model.state.value
        assertEquals(FieldError.NAME_REQUIRED, state.nameError)
        assertEquals(FieldError.EMAIL_REQUIRED, state.emailError)
        assertEquals(FieldError.PASSWORD_REQUIRED, state.passwordError)
        assertEquals(FieldError.CONFIRM_PASSWORD_REQUIRED, state.confirmPasswordError)
        assertFalse(fx.repository.isAuthenticated)
    }

    @Test
    fun `a too-short name is rejected`() = runTest {
        val fx = fixture(backgroundScope)
        fx.model.onNameChange("A")

        assertFalse(fx.model.submit())

        assertEquals(FieldError.NAME_TOO_SHORT, fx.model.state.value.nameError)
    }

    @Test
    fun `a malformed email is rejected`() = runTest {
        val fx = fixture(backgroundScope)
        fx.model.onEmailChange("not-an-email")

        assertFalse(fx.model.submit())

        assertEquals(FieldError.EMAIL_INVALID, fx.model.state.value.emailError)
    }

    @Test
    fun `a too-short password is rejected`() = runTest {
        val fx = fixture(backgroundScope)
        fx.model.onPasswordChange("short")
        fx.model.onConfirmPasswordChange("short")

        assertFalse(fx.model.submit())

        assertEquals(FieldError.PASSWORD_TOO_SHORT, fx.model.state.value.passwordError)
    }

    @Test
    fun `mismatched passwords are rejected`() = runTest {
        val fx = fixture(backgroundScope)
        fx.model.fillValidForm()
        fx.model.onConfirmPasswordChange("different-password")

        assertFalse(fx.model.submit())

        assertEquals(FieldError.CONFIRM_PASSWORD_MISMATCH, fx.model.state.value.confirmPasswordError)
    }

    @Test
    fun `editing a field clears its inline error`() = runTest {
        val fx = fixture(backgroundScope)
        assertFalse(fx.model.submit())
        assertEquals(FieldError.EMAIL_REQUIRED, fx.model.state.value.emailError)

        fx.model.onEmailChange("ana@example.com")

        assertNull(fx.model.state.value.emailError)
    }

    @Test
    fun `valid details register the user and land in onboarding`() = runTest {
        val fx = fixture(backgroundScope)
        fx.model.fillValidForm()

        assertTrue(fx.model.submit())

        val state = fx.model.state.value
        assertTrue(state.isSuccess)
        assertFalse(state.isLoading)
        assertNull(state.error)
        assertEquals("", state.password)
        assertEquals("", state.confirmPassword)
        assertTrue(fx.repository.isAuthenticated)
        assertIs<SessionState.Onboarding>(fx.session.state.value)
    }

    @Test
    fun `a rejected registration surfaces a message and stays on the form`() = runTest {
        val fx = fixture(backgroundScope, error = ApiException.HttpError(409, null))
        fx.model.fillValidForm()

        assertFalse(fx.model.submit())

        val state = fx.model.state.value
        assertEquals(AuthError.LOGIN_FAILED, state.error)
        assertFalse(state.isLoading)
        assertFalse(state.isSuccess)
        assertEquals("secret-password", state.password)
    }

    @Test
    fun `canSubmit reflects the field content`() = runTest {
        val fx = fixture(backgroundScope)
        assertFalse(fx.model.state.value.canSubmit)

        fx.model.fillValidForm()

        assertTrue(fx.model.state.value.canSubmit)
    }

    @Test
    fun `submit propagates cancellation`() = runTest {
        val fx = fixture(backgroundScope, error = CancellationException("cancelled"))
        fx.model.fillValidForm()

        assertFailsWith<CancellationException> { fx.model.submit() }

        assertFalse(fx.model.state.value.isLoading)
    }
}
