package com.nutriplan.shared.commerce

import com.nutriplan.shared.data.model.FulfillmentProvider
import com.nutriplan.shared.data.model.KitchenAvailability
import com.nutriplan.shared.data.repository.CommerceUseCases
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.withContext

/** Observable state of the fulfillment picker (COM-607): which way the order is fulfilled. */
data class FulfillmentPickerUiState(
    val isLoading: Boolean = false,
    /** `dark_kitchen`, `grocery_delivery` or `pickup`; the option the user settled on. */
    val fulfillmentType: String? = null,
    /** The dark kitchen's answer for the chosen zip code and day, once asked. */
    val darkKitchen: KitchenAvailability? = null,
    val providersLoading: Boolean = false,
    /** The grocery providers that can deliver, once asked; empty until grocery delivery is chosen. */
    val providers: List<FulfillmentProvider> = emptyList(),
    /** The grocery provider the user picked; required for `grocery_delivery`. */
    val providerId: String? = null,
    /** Whether the fulfillment step can be completed as it stands. */
    val canProceed: Boolean = false,
    /** What is missing on the step, after the user tried to proceed; null when nothing is missing. */
    val error: CheckoutStepError? = null,
)

/**
 * Chooses how an order is fulfilled (COM-607) over the commerce use cases: a dark kitchen (its
 * availability for the zip code and day decides), a grocery delivery (the providers decide) or
 * pickup. The user picks a way; the answer is looked up server-side and the pickup/grocery/dark-kitchen
 * paths then say whether the fulfillment can go through.
 *
 * - A dark kitchen the area does not serve has [CheckoutStepError.AREA_NOT_SERVED]; the user cannot
 *   proceed until the kitchen serves the address (or the user picks a delivery option it does).
 * - Grocery delivery requires a provider: without one, [FulfillmentPickerUiState.canProceed] is
 *   false and the picker waits for the user to choose.
 * - Pickup needs no answer and is immediately proceedable.
 *
 * The functions are `suspend` where they call the server, so the UI owns the coroutine scope; the
 * state is a [StateFlow] the screens collect.
 */
class FulfillmentPickerViewModel(
    private val useCases: CommerceUseCases,
    private val io: CoroutineDispatcher = Dispatchers.IO,
) {

    private val _state = MutableStateFlow(FulfillmentPickerUiState())
    val state: StateFlow<FulfillmentPickerUiState> = _state.asStateFlow()

    /**
     * Choose how the order is fulfilled. [zipCode] is the delivery address's Mexican zip code and
     * [deliveryDate] the ISO day it is for; the dark kitchen answers for that pair.
     */
    suspend fun start(fulfillmentType: String, zipCode: String, deliveryDate: String? = null) {
        _state.update {
            it.copy(
                fulfillmentType = fulfillmentType,
                providerId = null,
                canProceed = false,
                error = null,
            )
        }
        when (fulfillmentType) {
            CheckoutDraft.PICKUP -> _state.update { it.copy(isLoading = false, canProceed = true) }

            CheckoutDraft.DARK_KITCHEN -> {
                _state.update { it.copy(isLoading = true) }
                val result = withContext(io) { useCases.deliveryOptions(zipCode, deliveryDate) }
                if (result is OrderResult.Success) {
                    val available = result.value.available
                    _state.update { state ->
                        state.copy(
                            isLoading = false,
                            darkKitchen = result.value,
                            canProceed = available,
                            error = if (available) null else CheckoutStepError.AREA_NOT_SERVED,
                        )
                    }
                } else {
                    _state.update { it.copy(isLoading = false, canProceed = false) }
                }
            }

            CheckoutDraft.GROCERY_DELIVERY -> {
                _state.update { it.copy(isLoading = true, providersLoading = true) }
                val result = withContext(io) { useCases.groceryProviders() }
                if (result is OrderResult.Success) {
                    _state.update { state ->
                        state.copy(
                            isLoading = false,
                            providersLoading = false,
                            providers = result.value,
                            canProceed = false,
                            error = null,
                        )
                    }
                } else {
                    _state.update { it.copy(isLoading = false, providersLoading = false, canProceed = false) }
                }
            }

            else -> Unit
        }
    }

    /** Choose the grocery provider a `grocery_delivery` order is fulfilled with. */
    fun selectProvider(providerId: String) {
        _state.update { state ->
            state.copy(
                providerId = providerId,
                error = null,
                canProceed = state.fulfillmentType == CheckoutDraft.GROCERY_DELIVERY &&
                    providerId.isNotBlank() &&
                    state.providers.any { it.id == providerId },
            )
        }
    }
}