package com.nutriplan.shared.commerce

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
}
