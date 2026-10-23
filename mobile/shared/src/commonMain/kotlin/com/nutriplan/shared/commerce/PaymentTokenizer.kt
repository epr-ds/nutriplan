package com.nutriplan.shared.commerce

/**
 * Turns a card (or wallet) the user enters into a provider token, on the device and inside the
 * payment provider's own SDK UI (Stripe / Conekta, COM-508). The app never sees the card number: it
 * only gets back a [NewPaymentMethod] holding the token and display details.
 *
 * The platform binds an implementation; while none is bound, the app offers no way to add a method.
 */
interface PaymentTokenizer {
    suspend fun tokenize(): TokenizationResult
}

/** The outcome of [PaymentTokenizer.tokenize]. */
sealed interface TokenizationResult {
    /** The provider tokenized the instrument. */
    data class Tokenized(val method: NewPaymentMethod) : TokenizationResult

    /** The user closed the provider's form. */
    data object Cancelled : TokenizationResult

    /** The provider could not tokenize it (declined, offline, SDK error). */
    data object Failed : TokenizationResult
}
