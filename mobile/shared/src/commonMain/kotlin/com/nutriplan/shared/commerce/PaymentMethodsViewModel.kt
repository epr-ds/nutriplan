package com.nutriplan.shared.commerce

import com.nutriplan.shared.data.model.PaymentMethod
import com.nutriplan.shared.data.repository.PaymentRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

/** Why adding a payment method did not work, beyond the [OrderError]s of the server call. */
enum class AddPaymentMethodError {
    /** The provider's SDK could not tokenize the card. */
    TOKENIZATION_FAILED,
}

/** Observable state of the payment-method screen (COM-603). */
data class PaymentMethodsUiState(
    val isLoading: Boolean = true,
    val methods: List<PaymentMethod> = emptyList(),
    /** Why the list could not be loaded; the list stays as it was. */
    val loadError: OrderError? = null,
    /** Why the last add or delete failed. */
    val actionError: OrderError? = null,
    val addError: AddPaymentMethodError? = null,
    /** Whether methods can be added on this device: a provider tokenizer is available (COM-508). */
    val canAdd: Boolean = false,
    val isAdding: Boolean = false,
    /** The method the user asked to delete, waiting for confirmation. */
    val confirmingDelete: PaymentMethod? = null,
    val isDeleting: Boolean = false,
    /** The server rejected the session: the screen sends the user to sign in again. */
    val sessionExpired: Boolean = false,
) {
    /** Loaded and nothing saved yet. */
    val isEmpty: Boolean get() = !isLoading && loadError == null && methods.isEmpty()
}

/**
 * Shared logic of the payment-method screen (COM-603), used by the Compose and SwiftUI screens, on
 * top of [PaymentRepository] (COM-506).
 *
 * - The list is always the server's: nothing about a card is stored on the device.
 * - A method is added only through the provider's [tokenizer] (COM-508), which shows the provider's
 *   own card form and gives back a token; the app never handles a card number. Without a tokenizer
 *   the screen offers no "Add".
 * - Deleting asks for confirmation first; a method that is already gone counts as deleted.
 *
 * The functions are `suspend` where they call the server so the UI owns the coroutine scope.
 */
class PaymentMethodsViewModel(
    private val repository: PaymentRepository,
    private val tokenizer: PaymentTokenizer? = null,
) {

    private val _state = MutableStateFlow(PaymentMethodsUiState(canAdd = tokenizer != null))
    val state: StateFlow<PaymentMethodsUiState> = _state.asStateFlow()

    /** Read the saved methods from the server. */
    suspend fun load() {
        _state.update { it.copy(isLoading = true) }
        when (val result = repository.paymentMethods()) {
            is OrderResult.Success -> _state.update { it.copy(isLoading = false, methods = result.value, loadError = null) }
            is OrderResult.Failure -> _state.update { it.withFailure(result.error).copy(isLoading = false, loadError = result.error) }
        }
    }

    /** Add a method through the provider's form. Returns true when one was saved. */
    suspend fun add(): Boolean {
        val tokenizer = tokenizer ?: return false
        if (_state.value.isAdding) return false
        _state.update { it.copy(isAdding = true, actionError = null, addError = null) }
        val method = when (val tokenized = tokenizer.tokenize()) {
            is TokenizationResult.Tokenized -> tokenized.method
            TokenizationResult.Cancelled -> {
                _state.update { it.copy(isAdding = false) }
                return false
            }
            TokenizationResult.Failed -> {
                _state.update { it.copy(isAdding = false, addError = AddPaymentMethodError.TOKENIZATION_FAILED) }
                return false
            }
        }
        return when (val result = repository.addPaymentMethod(method)) {
            is OrderResult.Success -> {
                _state.update { it.copy(isAdding = false) }
                load()
                true
            }
            is OrderResult.Failure -> {
                _state.update { it.withFailure(result.error).copy(isAdding = false, actionError = result.error) }
                false
            }
        }
    }

    /** Ask to delete [method]; nothing happens until [confirmDelete]. */
    fun requestDelete(method: PaymentMethod) {
        _state.update { it.copy(confirmingDelete = method, actionError = null) }
    }

    fun cancelDelete() {
        _state.update { it.copy(confirmingDelete = null) }
    }

    /** Delete the method waiting for confirmation. */
    suspend fun confirmDelete() {
        val method = _state.value.confirmingDelete ?: return
        _state.update { it.copy(isDeleting = true) }
        // A method that is already gone is what the user wanted.
        val error = when (val result = repository.deletePaymentMethod(method.id)) {
            is OrderResult.Success -> null
            is OrderResult.Failure -> result.error.takeIf { it != OrderError.NOT_FOUND }
        }
        if (error == null) {
            _state.update { it.copy(isDeleting = false, confirmingDelete = null) }
            load()
        } else {
            _state.update { it.withFailure(error).copy(isDeleting = false, confirmingDelete = null, actionError = error) }
        }
    }

    /** Dismiss the error message of the last add or delete. */
    fun dismissError() {
        _state.update { it.copy(actionError = null, addError = null) }
    }

    private fun PaymentMethodsUiState.withFailure(error: OrderError) =
        if (error == OrderError.SESSION_EXPIRED) copy(sessionExpired = true) else this
}
