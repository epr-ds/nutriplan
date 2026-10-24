package com.nutriplan.shared.commerce

import com.nutriplan.shared.data.local.AddressBookStore
import com.nutriplan.shared.data.local.SavedAddress
import com.nutriplan.shared.data.model.FulfillmentProvider
import com.nutriplan.shared.data.model.MealPlanSummary
import com.nutriplan.shared.data.model.Order
import com.nutriplan.shared.data.model.OrderQuote
import com.nutriplan.shared.planning.IsoDate
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.IO
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
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

    /** No payment method was chosen (COM-608). */
    PAYMENT_REQUIRED,

    /** The payment provider could not verify the card (COM-608). */
    CARD_NOT_VERIFIED,
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
    /** How the user pays (COM-608): `credit_card`, `oxxo`, `spei` or `paypal`. */
    val paymentType: String? = null,
    /** A card can be paid with on this device: the provider's tokenizer is available (COM-508). */
    val canPayByCard: Boolean = false,
    /** Save the card paid with for the next checkout. */
    val saveCard: Boolean = false,
    val isPlacing: Boolean = false,
    /** The order once it was placed; the screen then shows the confirmation (COM-608). */
    val placedOrder: Order? = null,
    /** The earlier order this checkout repeats (COM-701), its delivery choices already filled in. */
    val reorderOf: Order? = null,
    /** The server rejected the session: the screen sends the user to sign in again. */
    val sessionExpired: Boolean = false,
) {
    val placedOrderId: String? get() = placedOrder?.id

    /** What is left to pay the placed order with (an OXXO voucher, a SPEI transfer, a PayPal approval). */
    val paymentInstructions: PaymentInstructions get() = placedOrder?.paymentInstructions() ?: PaymentInstructions.None

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
 * Paying (COM-608): the review asks how to pay. A card goes through the provider's [tokenizer] when
 * the order is placed (only offered when there is one), and can be saved for next time; OXXO, SPEI
 * and PayPal need no card and leave the order `pending` with [CheckoutUiState.paymentInstructions].
 * A retry after a failure reuses the card already tokenized, so the request -- and its idempotency
 * key -- stays the same and the order is never created or charged twice. The placed order is kept
 * for the confirmation.
 *
 * The functions are `suspend` where they call the server or the device's store, so the UI owns the
 * coroutine scope.
 *
 * @param loadPlans the user's meal plans (the Dietary client).
 * @param addressBook the delivery addresses kept on the device.
 * @param tokenizer the payment provider's card form (COM-508); without one, cards are not offered.
 */
class CheckoutViewModel(
    private val useCases: CommerceUseCases,
    private val loadPlans: suspend () -> List<MealPlanSummary>,
    private val addressBook: AddressBookStore,
    private val io: CoroutineDispatcher = Dispatchers.IO,
    private val tokenizer: PaymentTokenizer? = null,
) {

    private val _state = MutableStateFlow(CheckoutUiState(canPayByCard = tokenizer != null))
    val state: StateFlow<CheckoutUiState> = _state.asStateFlow()

    /** The card tokenized for this checkout, reused when placing is retried. */
    private var tokenizedCard: NewPaymentMethod? = null

    /** Choose how to pay; a card is only offered when the device can tokenize one. */
    fun selectPayment(type: String) {
        if (type !in PAYMENT_TYPES || (type in CARD_TYPES && tokenizer == null)) return
        if (type != _state.value.paymentType) tokenizedCard = null
        _state.update { it.copy(paymentType = type, stepError = null) }
    }

    fun onSaveCardChange(save: Boolean) {
        _state.update { it.copy(saveCard = save) }
    }

    /**
     * Load the plans and addresses; [today] (ISO, from the platform) is the default delivery day.
     * With [reorderOf] (an order id, COM-701) the earlier order's fulfillment type, store and
     * delivery address are chosen too, so the user only picks the plan and the day.
     */
    suspend fun start(today: String, planId: String? = null, reorderOf: String? = null) {
        if (reorderOf != null) prefillFrom(reorderOf)
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

    /**
     * Fill in the delivery choices of order [orderId]: its fulfillment type, its store (when it is
     * still offered) and its address (when it is in the address book). The plan, day and slot are
     * the user's to choose again. An order that cannot be read leaves an ordinary checkout.
     */
    private suspend fun prefillFrom(orderId: String) {
        // The device's copy is enough (and works offline); without one, the server's answer.
        val order = (useCases.order(orderId).first() as? OrderResult.Success)?.value?.value ?: return
        val type = order.fulfillmentType?.takeIf { it in CheckoutDraft.FULFILLMENT_TYPES } ?: return
        _state.update { it.copy(reorderOf = order) }
        refreshAddresses()
        order.deliveryAddress?.let { address ->
            _state.value.addresses.firstOrNull { it.address == address }?.let { selectAddress(it.id) }
        }
        selectFulfillment(type)
        order.provider?.id?.takeIf { id -> _state.value.providers.any { it.id == id } }?.let(::selectProvider)
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

    /**
     * Pay for and place the order the user reviewed. Returns true when it was placed
     * ([CheckoutUiState.placedOrder]).
     */
    suspend fun placeOrder(): Boolean {
        val reviewed = _state.value.toDraft() ?: return false
        if (_state.value.isPlacing) return false
        val type = _state.value.paymentType
        if (type == null) {
            _state.update { it.copy(stepError = CheckoutStepError.PAYMENT_REQUIRED) }
            return false
        }
        _state.update { it.copy(isPlacing = true, error = null, stepError = null) }
        val payment = if (type in CARD_TYPES) {
            tokenizedCard ?: tokenizeCard() ?: return false
        } else {
            NewPaymentMethod.withoutToken(type)
        }
        val draft = reviewed.copy(payment = payment, savePaymentMethod = type in CARD_TYPES && _state.value.saveCard)
        return when (val result = useCases.placeOrder(draft)) {
            is OrderResult.Success -> {
                tokenizedCard = null
                _state.update { it.copy(isPlacing = false, placedOrder = result.value) }
                true
            }
            is OrderResult.Failure -> {
                // A declined or refused card will not do better next time; anything else may have
                // reached the server, so the same card is retried with the same request.
                if (result.error == OrderError.PAYMENT_DECLINED || result.error == OrderError.REJECTED) tokenizedCard = null
                fail(result.error)
                _state.update { it.copy(isPlacing = false) }
                false
            }
        }
    }

    /** Tokenize a card through the provider's form; null (and the reason shown) when there is none. */
    private suspend fun tokenizeCard(): NewPaymentMethod? {
        val result = tokenizer?.tokenize() ?: TokenizationResult.Failed
        return when (result) {
            is TokenizationResult.Tokenized -> result.method.also { tokenizedCard = it }
            TokenizationResult.Cancelled -> {
                _state.update { it.copy(isPlacing = false) }
                null
            }
            TokenizationResult.Failed -> {
                _state.update { it.copy(isPlacing = false, stepError = CheckoutStepError.CARD_NOT_VERIFIED) }
                null
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
