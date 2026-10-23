package com.nutriplan.shared.commerce

import com.nutriplan.shared.data.model.PaymentMethodRequest
import com.nutriplan.shared.data.model.SavePaymentMethodRequest
import com.nutriplan.shared.data.repository.looksLikeCardNumber

/**
 * A payment method to save (COM-506): the token the payment provider's SDK minted on the device
 * (COM-508) and the non-sensitive details to show it by. A card number or CVV is never part of it;
 * only the token crosses the app's boundary.
 *
 * [toString] never prints the token, so the value is safe in logs and crash reports.
 */
class NewPaymentMethod(
    /** `credit_card`, `debit_card`, `paypal`, `oxxo` or `spei`. */
    val type: String,
    /** The provider's token for the instrument. */
    val token: String,
    val brand: String? = null,
    /** The last four digits of a card, for display. */
    val last4: String? = null,
    val expMonth: Int? = null,
    val expYear: Int? = null,
) {
    override fun equals(other: Any?): Boolean =
        other is NewPaymentMethod && type == other.type && token == other.token && brand == other.brand &&
            last4 == other.last4 && expMonth == other.expMonth && expYear == other.expYear

    override fun hashCode(): Int = listOf(type, token, brand, last4, expMonth, expYear).hashCode()

    override fun toString(): String =
        "NewPaymentMethod(type=$type, token=<redacted>, brand=$brand, last4=$last4, expMonth=$expMonth, expYear=$expYear)"

    companion object {
        /** OXXO, SPEI or PayPal at checkout: no card, so no token (COM-608). */
        fun withoutToken(type: String): NewPaymentMethod = NewPaymentMethod(type = type, token = "")
    }
}

/** The payment types the contract accepts (`PaymentMethodRequest.type`). */
internal val PAYMENT_TYPES = setOf("credit_card", "debit_card", "paypal", "oxxo", "spei")

private const val LAST4_LENGTH = 4
private const val MONTHS = 12
private const val MIN_EXP_YEAR = 2000

/**
 * The token to send, trimmed, or null when this must not be sent: an unknown type, a blank token, or
 * a "token" that is really a card number (see [looksLikeCardNumber]).
 */
internal fun NewPaymentMethod.sendableToken(): String? =
    token.trim().takeIf { type in PAYMENT_TYPES && it.isNotEmpty() && !it.looksLikeCardNumber() }

/** The `SavePaymentMethodRequest` for this method (COM-506), or null when it must not be sent. */
internal fun NewPaymentMethod.toSaveRequest(): SavePaymentMethodRequest? {
    val cleanToken = sendableToken() ?: return null
    val validDetails = (last4 == null || (last4.length == LAST4_LENGTH && last4.all(Char::isDigit))) &&
        (expMonth == null || expMonth in 1..MONTHS) &&
        (expYear == null || expYear >= MIN_EXP_YEAR)
    if (!validDetails) return null
    return SavePaymentMethodRequest(
        type = type,
        token = cleanToken,
        brand = brand?.trim()?.takeIf(String::isNotEmpty),
        last4 = last4,
        expMonth = expMonth,
        expYear = expYear,
    )
}

/** The card types, charged at once and the only ones that need a token (COM-608). */
internal val CARD_TYPES = setOf("credit_card", "debit_card")

/**
 * How an order is paid with this method (`PaymentMethodRequest`, COM-507), or null when it must not
 * be sent. A card needs a sendable token; OXXO, SPEI and PayPal need none (COM-608), and a card
 * number is never sent in any case.
 */
internal fun NewPaymentMethod.toOrderPayment(): PaymentMethodRequest? {
    if (type !in PAYMENT_TYPES) return null
    if (type in CARD_TYPES) return sendableToken()?.let { PaymentMethodRequest(type = type, token = it) }
    val clean = token.trim()
    if (clean.looksLikeCardNumber()) return null
    return PaymentMethodRequest(type = type, token = clean.takeIf(String::isNotEmpty))
}
