package com.nutriplan.shared.commerce

import com.nutriplan.shared.data.model.CreateOrderRequest
import com.nutriplan.shared.data.model.OrderAddress
import com.nutriplan.shared.planning.IsoDate

/** A checkout field that is missing or invalid, so a form can point at it (COM-507). */
enum class CheckoutField {
    MEAL_PLAN,
    FULFILLMENT_TYPE,
    PROVIDER,
    STREET,
    CITY,
    STATE,
    ZIP_CODE,
    COUNTRY,
    DELIVERY_DATE,
    TIME_SLOT,
    PAYMENT,
}

/**
 * What the user chose at checkout (COM-507): the meal plan to order, how it is fulfilled, where and
 * when it is delivered, and how it is paid. [problems] checks it against the contract's
 * `CreateOrderRequest` before anything is sent.
 *
 * With [savePaymentMethod] a card or wallet paid with is also saved for the next checkout, once the
 * order went through.
 */
data class CheckoutDraft(
    val mealPlanId: String,
    /** `dark_kitchen`, `grocery_delivery` or `pickup`. */
    val fulfillmentType: String,
    val address: OrderAddress,
    /** ISO date, e.g. `2026-11-02`. */
    val deliveryDate: String,
    val deliveryTimeSlot: String,
    /** The grocery provider; required for `grocery_delivery`. */
    val providerId: String? = null,
    /** How to pay now; without one the order is created unpaid (`pending`). */
    val payment: NewPaymentMethod? = null,
    val notes: String? = null,
    val savePaymentMethod: Boolean = false,
) {
    /** The fields the contract would refuse; empty when the draft can be sent. */
    fun problems(): Set<CheckoutField> = buildSet {
        if (mealPlanId.isBlank()) add(CheckoutField.MEAL_PLAN)
        if (fulfillmentType !in FULFILLMENT_TYPES) add(CheckoutField.FULFILLMENT_TYPE)
        if (fulfillmentType == GROCERY_DELIVERY && providerId.isNullOrBlank()) add(CheckoutField.PROVIDER)
        if (address.street.isBlank()) add(CheckoutField.STREET)
        if (address.city.isBlank()) add(CheckoutField.CITY)
        if (address.state.isBlank()) add(CheckoutField.STATE)
        if (!address.zipCode.trim().isMexicanZipCode()) add(CheckoutField.ZIP_CODE)
        if (address.country.isBlank()) add(CheckoutField.COUNTRY)
        if (!IsoDate.isValid(deliveryDate.trim())) add(CheckoutField.DELIVERY_DATE)
        if (deliveryTimeSlot.isBlank()) add(CheckoutField.TIME_SLOT)
        if (payment != null && payment.toOrderPayment() == null) add(CheckoutField.PAYMENT)
    }

    /** The request to send, trimmed with blank optional fields left out; null when there are [problems]. */
    internal fun toRequest(): CreateOrderRequest? {
        if (problems().isNotEmpty()) return null
        return CreateOrderRequest(
            mealPlanId = mealPlanId.trim(),
            fulfillmentType = fulfillmentType,
            providerId = providerId.cleaned(),
            deliveryAddress = OrderAddress(
                street = address.street.trim(),
                apartment = address.apartment.cleaned(),
                city = address.city.trim(),
                state = address.state.trim(),
                zipCode = address.zipCode.trim(),
                country = address.country.trim(),
                instructions = address.instructions.cleaned(),
            ),
            deliveryDate = deliveryDate.trim(),
            deliveryTimeSlot = deliveryTimeSlot.trim(),
            paymentMethod = payment?.toOrderPayment(),
            notes = notes.cleaned(),
        )
    }

    private fun String?.cleaned(): String? = this?.trim()?.takeIf(String::isNotEmpty)

    private companion object {
        const val GROCERY_DELIVERY = "grocery_delivery"
        val FULFILLMENT_TYPES = setOf("dark_kitchen", GROCERY_DELIVERY, "pickup")
    }
}

private const val ZIP_LENGTH = 5

/** The contract's rule for a postal code: five digits (Mexico). */
internal fun String.isMexicanZipCode(): Boolean = length == ZIP_LENGTH && all(Char::isDigit)
