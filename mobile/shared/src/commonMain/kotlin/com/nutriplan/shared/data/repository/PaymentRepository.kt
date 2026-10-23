package com.nutriplan.shared.data.repository

import com.nutriplan.shared.commerce.NewPaymentMethod
import com.nutriplan.shared.commerce.OrderError
import com.nutriplan.shared.commerce.OrderResult
import com.nutriplan.shared.commerce.toOrderError
import com.nutriplan.shared.data.model.PaymentMethod
import com.nutriplan.shared.data.model.SavePaymentMethodRequest
import kotlin.coroutines.cancellation.CancellationException

/**
 * The user's saved payment methods (COM-506), shared by the Compose and SwiftUI checkout: list, add
 * and delete, each returning an [OrderResult] with the same [OrderError] mapping as the other
 * Commerce operations.
 *
 * Payment data is handled as little as possible:
 * - **Tokens only.** A method is added from a [NewPaymentMethod]: the provider's token (minted on the
 *   device by its SDK, COM-508) and display details. The server never returns the token either, so
 *   a listed [PaymentMethod] only has an id and those details.
 * - **Nothing is stored on the device.** There is no local copy (no database table, no cache): the
 *   list is always the server's, and nothing about a card outlives the request.
 * - **A card number is refused, not sent.** A "token" that is really a card number (12-19 digits that
 *   pass the Luhn check), or malformed details, is [OrderError.REJECTED] without a call -- a safety
 *   net against a wiring mistake ever sending card data to the server.
 */
class PaymentRepository(private val remote: CommerceRepository) {

    /** The user's saved payment methods, newest first. */
    suspend fun paymentMethods(): OrderResult<List<PaymentMethod>> = call { remote.listPaymentMethods() }

    /** Save [method] for reuse at checkout; returns the saved method (its id and display details). */
    suspend fun addPaymentMethod(method: NewPaymentMethod): OrderResult<PaymentMethod> {
        val request = method.toRequest() ?: return OrderResult.Failure(OrderError.REJECTED)
        return call { remote.savePaymentMethod(request) }
    }

    /** Delete a saved payment method. One that is already gone is [OrderError.NOT_FOUND]. */
    suspend fun deletePaymentMethod(paymentMethodId: String): OrderResult<Unit> {
        if (paymentMethodId.isBlank()) return OrderResult.Failure(OrderError.REJECTED)
        return call { remote.deletePaymentMethod(paymentMethodId) }
    }

    /** The wire request for a valid [NewPaymentMethod], or null when it must not be sent. */
    private fun NewPaymentMethod.toRequest(): SavePaymentMethodRequest? {
        val cleanToken = token.trim()
        val valid = type in PAYMENT_TYPES &&
            cleanToken.isNotEmpty() &&
            !cleanToken.looksLikeCardNumber() &&
            (last4 == null || (last4.length == LAST4_LENGTH && last4.all(Char::isDigit))) &&
            (expMonth == null || expMonth in 1..MONTHS) &&
            (expYear == null || expYear >= MIN_EXP_YEAR)
        if (!valid) return null
        return SavePaymentMethodRequest(
            type = type,
            token = cleanToken,
            brand = brand?.trim()?.takeIf(String::isNotEmpty),
            last4 = last4,
            expMonth = expMonth,
            expYear = expYear,
        )
    }

    /** Run a server call, turning a failure into a typed result (cancellation is never swallowed). */
    private suspend fun <T> call(block: suspend () -> T): OrderResult<T> =
        try {
            OrderResult.Success(block())
        } catch (e: CancellationException) {
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            OrderResult.Failure(e.toOrderError())
        }

    private companion object {
        val PAYMENT_TYPES = setOf("credit_card", "debit_card", "paypal", "oxxo", "spei")
        const val LAST4_LENGTH = 4
        const val MONTHS = 12
        const val MIN_EXP_YEAR = 2000
    }
}

/**
 * Whether this looks like a primary account number rather than a token: only digits (spaces and
 * dashes aside), 12-19 of them, passing the Luhn checksum every card number carries.
 */
internal fun String.looksLikeCardNumber(): Boolean {
    if (any { !it.isDigit() && it != ' ' && it != '-' }) return false
    val digits = filter(Char::isDigit)
    if (digits.length !in 12..19) return false
    val sum = digits.reversed().mapIndexed { index, char ->
        val digit = char - '0'
        if (index % 2 == 1) (digit * 2).let { if (it > 9) it - 9 else it } else digit
    }.sum()
    return sum % 10 == 0
}
