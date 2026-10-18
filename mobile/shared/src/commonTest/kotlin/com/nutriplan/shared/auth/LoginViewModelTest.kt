package com.nutriplan.shared.auth

import com.nutriplan.shared.data.network.ApiException
import com.nutriplan.shared.session.DefaultSessionManager
import com.nutriplan.shared.session.FakeAuthRepository
import com.nutriplan.shared.session.Login
import com.nutriplan.shared.session.authResponse
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class LoginViewModelTest {

    private fun viewModel(
        scope: CoroutineScope,
        error: Throwable? = null,
    ): Pair<LoginViewModel, FakeAuthRepository> {
        val repository = FakeAuthRepository(
            response = authResponse(onboardingComplete = false),
            error = error,
        )
        val login = Login(repository, DefaultSessionManager(FakeAuthRepository(), scope))
        return LoginViewModel(login) to repository
    }

    @Test
    fun `blank fields are rejected with inline errors before any request`() = runTest {
        val (model, repository) = viewModel(backgroundScope)

        assertFalse(model.submit())

        assertEquals(FieldError.EMAIL_REQUIRED, model.state.value.emailError)
        assertEquals(FieldError.PASSWORD_REQUIRED, model.state.value.passwordError)
        assertNull(model.state.value.error)
        assertFalse(repository.isAuthenticated)
    }

    @Test
    fun `a malformed email is rejected`() = runTest {
        val (model, _) = viewModel(backgroundScope)
        model.onEmailChange("not-an-email")
        model.onPasswordChange("secret-password")

        assertFalse(model.submit())

        assertEquals(FieldError.EMAIL_INVALID, model.state.value.emailError)
        assertNull(model.state.value.passwordError)
    }

    @Test
    fun `editing a field clears its inline error`() = runTest {
        val (model, _) = viewModel(backgroundScope)
        assertFalse(model.submit())
        assertEquals(FieldError.EMAIL_REQUIRED, model.state.value.emailError)

        model.onEmailChange("ana@example.com")

        assertNull(model.state.value.emailError)
    }

    @Test
    fun `valid credentials sign in and flag success`() = runTest {
        val (model, repository) = viewModel(backgroundScope)
        model.onEmailChange("  ana@example.com ")
        model.onPasswordChange("secret-password")

        assertTrue(model.submit())

        val state = model.state.value
        assertTrue(state.isSuccess)
        assertFalse(state.isLoading)
        assertNull(state.error)
        assertEquals("", state.password)
        assertTrue(repository.isAuthenticated)
    }

    @Test
    fun `a rejected login surfaces a message and stays on the form`() = runTest {
        val (model, _) = viewModel(backgroundScope, error = ApiException.HttpError(401, null))
        model.onEmailChange("ana@example.com")
        model.onPasswordChange("wrong-password")

        assertFalse(model.submit())

        val state = model.state.value
        assertEquals(AuthError.INVALID_CREDENTIALS, state.error)
        assertFalse(state.isLoading)
        assertFalse(state.isSuccess)
        assertEquals("wrong-password", state.password)
    }

    @Test
    fun `canSubmit reflects the field content`() = runTest {
        val (model, _) = viewModel(backgroundScope)
        assertFalse(model.state.value.canSubmit)

        model.onEmailChange("ana@example.com")
        assertFalse(model.state.value.canSubmit)

        model.onPasswordChange("secret-password")
        assertTrue(model.state.value.canSubmit)
    }

    @Test
    fun `submit propagates cancellation`() = runTest {
        val (model, _) = viewModel(backgroundScope, error = CancellationException("cancelled"))
        model.onEmailChange("ana@example.com")
        model.onPasswordChange("secret-password")

        assertFailsWith<CancellationException> { model.submit() }

        assertFalse(model.state.value.isLoading)
    }
}
