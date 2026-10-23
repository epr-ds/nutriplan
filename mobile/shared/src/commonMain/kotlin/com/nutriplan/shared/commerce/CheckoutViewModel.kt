package com.nutriplan.shared.commerce

import com.nutriplan.shared.data.local.AddressBookStore
import com.nutriplan.shared.data.local.SavedAddress
import com.nutriplan.shared.data.model.FulfillmentProvider
import com.nutriplan.shared.data.model.MealPlanSummary
import com.nutriplan.shared.data.model.OrderQuote
import com.nutriplan.shared.planning.IsoDate
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.IO
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.withContext
import kotlin.coroutines.cancellation.CancellationException

/** The steps of the checkout (COM-605), in order. */
enum class CheckoutStep { PLAN, FULFILLMENT, ADDRESS, SLOT, REVIEW }

/** What is missing before the user can move on from a step. Locale-neutral. */
enum class CheckoutStepError {
    PLAN_REQUIRED,
    FULFILLMENT_REQUIRED,
    PROVIDER_REQUIRED,
    ADDRESS_REQUIRED,
    DATE_INVALID,
    SLOT_REQUIRED,

    /** The dark kitchen does not deliver to the chosen address, or not on that day. */
    AREA_NOT_SERVED,
}

/** Observable state of the checkout stepper (COM-605). */
data class CheckoutUiState(
    val step: CheckoutStep = CheckoutStep.PLAN,
    val plansLoading: Boolean = true,
    val plans: List<MealPlanSummary> = emptyList(),
    val planId: String? = null,
    /** `dark_kitchen`, `grocery_delivery` or `pickup`. */
    val fulfillmentType: String? = null,
    val providersLoading: Boolean = false,
    val providers: List<FulfillmentProvider> = emptyList(),
    val providerId: String? = null,
    val addresses: List<SavedAddress> = emptyList(),
    val addressId: Long? = null,
    /** ISO date. */
    val deliveryDate: String = "",
    val slotsLoading: Boolean = false,
    val slots: List<String> = emptyList(),
    val timeSlot: String? = null,
    val quoteLoading: Boolean = false,
    val quote: OrderQuote? = null,
    /** What is missing on the current step, after the user tried to move on. */
    val stepError: CheckoutStepError? = null,
    /** Why the last server call (plans, providers, slots, quote or placing the order) failed. */
    val error: OrderError? = null,
    val isPlacing: Boolean = false,
    /** Set once the order was placed; the screen then opens it. */
    val placedOrderId: String? = null,
    /** The server rejected the session: the screen sends the user to sign in again. */
    val sessionExpired: Boolean = false,
) {
    val selectedPlan: MealPlanSummary? get() = plans.firstOrNull { it.id == planId }
    val selectedAddress: SavedAddress? get() = addresses.firstOrNull { it.id == addressId }
    val selectedProvider: FulfillmentProvider? get() = providers.firstOrNull { it.id == providerId }

    /** Steps before the current one, which the user can go back to and edit. */
    fun canEdit(step: CheckoutStep): Boolean = step.ordinal < this.step.ordinal
}

/**
 * Shared logic of the checkout stepper (COM-605), used by the Compose and SwiftUI screens: choose a
 * meal plan, how it is fulfilled (dark kitchen, grocery delivery with a provider, or pickup), the
 * delivery address from the address book (COM-601), the day and time slot, and review the itemized
 * price (`POST /orders/quote`) before placing the order through [CommerceUseCases].
 *
 * - Each step is checked before moving on ([next]), the way the contract checks the order: a plan, a
 *   fulfillment type, a provider for grocery delivery, an address, a real date and a time slot.
 * - A dark kitchen's time slots come from its availability for the address's zip code and the day
 *   (COM-302); an area it does not serve cannot be chosen. Grocery delivery and pickup offer the
 *   standard delivery windows.
 * - [back] and [edit] return to earlier steps; changing an earlier choice clears what depended on it
 *   (a new fulfillment type clears the provider and slot, a new address or day the slot) and the
 *   price, which the review step asks for again.
 *
 * Payment selection comes with COM-608; until then the order is placed without one and is
 * `pending`. The functions are `suspend` where they call the server or the device's store, so the UI
 * owns the coroutine scope.
 *
 * @param loadPlans the user's meal plans (the Dietary client).
 * @param addressBook the delivery addresses kept on the device.
 */
class CheckoutViewModel(
    private val useCases: CommerceUseCases,
    private val loadPlans: suspend () -> List<MealPlanSummary>,
    private val addressBook: AddressBookStore,
    private val io: CoroutineDispatcher = Dispatchers.IO,
) {

    private val _state = MutableStateFlow(CheckoutUiState())
    val state: StateFlow<CheckoutUiState> = _state.asStateFlow()

    /** Load the plans and addresses; [today] (ISO, from the platform) is the default delivery day. */
    suspend fun start(today: String, planId: String? = null) {
        _state.update { it.copy(deliveryDate = it.deliveryDate.ifEmpty { today }, planId = planId ?: it.planId) }
        refreshAddresses()
        val plans = try {
            loadPlans()
        } catch (e: CancellationException) {
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            fail(e.toOrderError())
            _state.update { it.copy(plansLoading = false) }
            return
        }
        _state.update { state ->
            state.copy(
                plansLoading = false,
                plans = plans,
                // A single plan is the obvious choice.
                planId = state.planId ?: plans.singleOrNull()?.id,
                error = null,
            )
        }
    }

    /** Re-read the address book (for example after the user added an address from the address step). */
    suspend fun refreshAddresses() {
        val addresses = try {
            withContext(io) { addressBook.getAll() }
        } catch (e: CancellationException) {
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            emptyList()
        }
        _state.update { state ->
            val kept = state.addressId?.takeIf { id -> addresses.any { it.id == id } }
            // The default (or most recently used) address is preselected.
            state.copy(addresses = addresses, addressId = kept ?: addresses.firstOrNull()?.id)
        }
    }

    fun selectPlan(planId: String) {
        _state.update { it.copy(planId = planId, quote = null, stepError = null) }
    }

    /** Choose how the order is fulfilled; grocery delivery then lists the providers to choose from. */
    suspend fun selectFulfillment(type: String) {
        if (type !in CheckoutDraft.FULFILLMENT_TYPES) return
        _state.update {
            it.copy(fulfillmentType = type, providerId = null, timeSlot = null, slots = emptyList(), quote = null, stepError = null)
        }
        if (type == CheckoutDraft.GROCERY_DELIVERY && _state.value.providers.isEmpty()) loadProviders()
    }

    fun selectProvider(providerId: String) {
        _state.update { it.copy(providerId = providerId, quote = null, stepError = null) }
    }

    fun selectAddress(addressId: Long) {
        _state.update { it.copy(addressId = addressId, timeSlot = null, slots = emptyList(), stepError = null) }
    }

    /** Change the delivery day (ISO); the time slots are looked up again for it. */
    suspend fun onDateChange(date: String) {
        _state.update { it.copy(deliveryDate = date, timeSlot = null, slots = emptyList(), stepError = null) }
        if (_state.value.step == CheckoutStep.SLOT) loadSlots()
    }

    fun selectSlot(slot: String) {
        _state.update { it.copy(timeSlot = slot, stepError = null) }
    }

    /** Check the current step and move to the next one, loading what it needs. Returns true when moved. */
    suspend fun next(): Boolean {
        val state = _state.value
        val problem = state.problemOn(state.step)
        if (problem != null) {
            _state.update { it.copy(stepError = problem) }
            return false
        }
        val nextStep = CheckoutStep.entries.getOrNull(state.step.ordinal + 1) ?: return false
        _state.update { it.copy(step = nextStep, stepError = null, error = null) }
        prepare(nextStep)
        return true
    }

    /** Load what [step] shows: the time slots, or the price. */
    private suspend fun prepare(step: CheckoutStep) {
        when (step) {
            CheckoutStep.SLOT -> if (_state.value.slots.isEmpty()) loadSlots()
            CheckoutStep.REVIEW -> loadQuote()
            else -> Unit
        }
    }

    /** Go back one step. Returns false on the first step (the screen then closes). */
    fun back(): Boolean {
        val previous = CheckoutStep.entries.getOrNull(_state.value.step.ordinal - 1) ?: return false
        _state.update { it.copy(step = previous, stepError = null, error = null) }
        return true
    }

    /** Return to an earlier [step] to change it. */
    suspend fun edit(step: CheckoutStep) {
        if (!_state.value.canEdit(step)) return
        _state.update { it.copy(step = step, stepError = null, error = null) }
        prepare(step)
    }

    /** Look the time slots up again for the chosen address and day (the slot step's retry). */
    suspend fun loadSlots() {
        val state = _state.value
        if (state.fulfillmentType != CheckoutDraft.DARK_KITCHEN) {
            _state.update { it.copy(slots = STANDARD_TIME_SLOTS, slotsLoading = false) }
            return
        }
        val zip = state.selectedAddress?.address?.zipCode ?: return
        if (!IsoDate.isValid(state.deliveryDate)) return
        _state.update { it.copy(slotsLoading = true) }
        when (val result = useCases.deliveryOptions(zip, state.deliveryDate)) {
            is OrderResult.Success -> _state.update {
                it.copy(
                    slotsLoading = false,
                    slots = if (result.value.available) result.value.timeSlots else emptyList(),
                    stepError = if (result.value.available) null else CheckoutStepError.AREA_NOT_SERVED,
                )
            }
            is OrderResult.Failure -> {
                fail(result.error)
                _state.update { it.copy(slotsLoading = false) }
            }
        }
    }

    /** Ask the server for the itemized price (the review step's retry). */
    suspend fun loadQuote() {
        val state = _state.value
        val planId = state.planId ?: return
        val type = state.fulfillmentType ?: return
        _state.update { it.copy(quoteLoading = true) }
        when (val result = useCases.quoteOrder(planId, type, state.providerId)) {
            is OrderResult.Success -> _state.update { it.copy(quoteLoading = false, quote = result.value, error = null) }
            is OrderResult.Failure -> {
                fail(result.error)
                _state.update { it.copy(quoteLoading = false) }
            }
        }
    }

    /** Place the order the user reviewed. Returns true when it was placed ([CheckoutUiState.placedOrderId]). */
    suspend fun placeOrder(): Boolean {
        val draft = _state.value.toDraft() ?: return false
        if (_state.value.isPlacing) return false
        _state.update { it.copy(isPlacing = true, error = null) }
        return when (val result = useCases.placeOrder(draft)) {
            is OrderResult.Success -> {
                _state.update { it.copy(isPlacing = false, placedOrderId = result.value.id) }
                true
            }
            is OrderResult.Failure -> {
                fail(result.error)
                _state.update { it.copy(isPlacing = false) }
                false
            }
        }
    }

    private suspend fun loadProviders() {
        _state.update { it.copy(providersLoading = true) }
        when (val result = useCases.groceryProviders()) {
            is OrderResult.Success -> _state.update { state ->
                state.copy(
                    providersLoading = false,
                    providers = result.value,
                    providerId = state.providerId ?: result.value.singleOrNull()?.id,
                )
            }
            is OrderResult.Failure -> {
                fail(result.error)
                _state.update { it.copy(providersLoading = false) }
            }
        }
    }

    private fun fail(error: OrderError) {
        _state.update { it.copy(error = error, sessionExpired = it.sessionExpired || error == OrderError.SESSION_EXPIRED) }
    }

    private fun CheckoutUiState.problemOn(step: CheckoutStep): CheckoutStepError? = when (step) {
        CheckoutStep.PLAN -> CheckoutStepError.PLAN_REQUIRED.takeIf { selectedPlan == null }
        CheckoutStep.FULFILLMENT -> when {
            fulfillmentType == null -> CheckoutStepError.FULFILLMENT_REQUIRED
            fulfillmentType == CheckoutDraft.GROCERY_DELIVERY && selectedProvider == null -> CheckoutStepError.PROVIDER_REQUIRED
            else -> null
        }
        CheckoutStep.ADDRESS -> CheckoutStepError.ADDRESS_REQUIRED.takeIf { selectedAddress == null }
        CheckoutStep.SLOT -> when {
            !IsoDate.isValid(deliveryDate) -> CheckoutStepError.DATE_INVALID
            fulfillmentType == CheckoutDraft.DARK_KITCHEN && !slotsLoading && slots.isEmpty() -> CheckoutStepError.AREA_NOT_SERVED
            timeSlot == null || timeSlot !in slots -> CheckoutStepError.SLOT_REQUIRED
            else -> null
        }
        CheckoutStep.REVIEW -> null
    }

    /** The order to place, once every step is complete. */
    private fun CheckoutUiState.toDraft(): CheckoutDraft? {
        if (CheckoutStep.entries.any { problemOn(it) != null }) return null
        return CheckoutDraft(
            mealPlanId = planId ?: return null,
            fulfillmentType = fulfillmentType ?: return null,
            address = selectedAddress?.address ?: return null,
            deliveryDate = deliveryDate,
            deliveryTimeSlot = timeSlot ?: return null,
            providerId = providerId.takeIf { fulfillmentType == CheckoutDraft.GROCERY_DELIVERY },
        )
    }

    internal companion object {
        /** The delivery windows offered when no kitchen schedule applies (grocery, pickup). */
        val STANDARD_TIME_SLOTS = listOf("09:00-11:00", "11:00-13:00", "13:00-15:00", "17:00-19:00", "19:00-21:00")
    }
}
