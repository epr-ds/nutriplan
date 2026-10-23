package com.nutriplan.shared.commerce

import com.nutriplan.shared.data.model.CreateOrderRequest
import com.nutriplan.shared.data.model.FulfillmentProvider
import com.nutriplan.shared.data.model.GrocerySearchItem
import com.nutriplan.shared.data.model.KitchenAvailability
import com.nutriplan.shared.data.model.Order
import com.nutriplan.shared.data.model.OrderQuote
import com.nutriplan.shared.data.model.OrderQuoteRequest
import com.nutriplan.shared.data.model.PaymentMethod
import com.nutriplan.shared.data.repository.FulfillmentRepository
import com.nutriplan.shared.data.repository.OrderRepository
import com.nutriplan.shared.data.repository.PaymentRepository
import com.nutriplan.shared.planning.IsoDate
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlin.random.Random

/**
 * The Commerce use cases (COM-507), shared by the Compose and SwiftUI screens: the whole order,
 * fulfillment and payment flow on top of [OrderRepository] (COM-504), [FulfillmentRepository]
 * (COM-505) and [PaymentRepository] (COM-506). Every one returns an [OrderResult] (or a flow of them)
 * instead of throwing, so a screen only has to handle a value or an [OrderError].
 *
 * Input is checked the way the contract (`commerce.openapi.yaml`) does before anything is sent, so a
 * request the server would refuse is [OrderError.REJECTED] without a call; [CheckoutDraft.problems]
 * says which fields to fix.
 *
 * Payment happens when the order is placed: a card is charged at once, while OXXO, SPEI and PayPal
 * leave the order `pending` with [paymentInstructions] for the user to follow.
 *
 * One instance per checkout screen: it remembers the `Idempotency-Key` of an order it could not
 * confirm, so retrying the same checkout after a dropped connection can never create -- or charge --
 * the order twice.
 */
class CommerceUseCases(
    private val orders: OrderRepository,
    private val fulfillment: FulfillmentRepository,
    private val payments: PaymentRepository,
    private val newIdempotencyKey: () -> String = ::randomIdempotencyKey,
) {

    private val placing = Mutex()

    /** The `Idempotency-Key` of each order request not yet confirmed, reused when it is retried. */
    private val pendingKeys = mutableMapOf<CreateOrderRequest, String>()

    // --- checkout ---

    /**
     * Place the order [draft] describes, paying with its payment method if it has one. An invalid
     * draft is [OrderError.REJECTED] without a call ([CheckoutDraft.problems] says why). Retrying the
     * same draft reuses the same idempotency key, so the server returns the first order instead of a
     * second one; calls are serialized, so a double tap is a retry too.
     */
    suspend fun placeOrder(draft: CheckoutDraft): OrderResult<Order> {
        val request = draft.toRequest() ?: return OrderResult.Failure(OrderError.REJECTED)
        val result = placing.withLock {
            val key = pendingKeys.getOrPut(request, newIdempotencyKey)
            orders.createOrder(request, idempotencyKey = key).also {
                if (it is OrderResult.Success) pendingKeys.remove(request)
            }
        }
        val payment = draft.payment
        if (result is OrderResult.Success && draft.savePaymentMethod && payment != null) {
            // Saving for next time is a convenience: it never fails an order that went through.
            payments.addPaymentMethod(payment)
        }
        return result
    }

    /**
     * What an order for [mealPlanId] would cost with [fulfillmentType] (COM-605): the itemized
     * lines, subtotal, delivery fee and total the order will get, with nothing created or charged.
     * A grocery quote needs [providerId]; input the contract refuses is [OrderError.REJECTED].
     */
    suspend fun quoteOrder(mealPlanId: String, fulfillmentType: String, providerId: String? = null): OrderResult<OrderQuote> {
        val provider = providerId?.trim()?.takeIf(String::isNotEmpty)
        val valid = mealPlanId.isNotBlank() &&
            fulfillmentType in CheckoutDraft.FULFILLMENT_TYPES &&
            (fulfillmentType != CheckoutDraft.GROCERY_DELIVERY || provider != null)
        if (!valid) return OrderResult.Failure(OrderError.REJECTED)
        return orders.quote(OrderQuoteRequest(mealPlanId.trim(), fulfillmentType, provider))
    }

    /** Whether a dark kitchen delivers to [zipCode] and when, optionally on [deliveryDate] (ISO date). */
    suspend fun deliveryOptions(zipCode: String, deliveryDate: String? = null): OrderResult<KitchenAvailability> {
        val date = deliveryDate?.trim()?.takeIf(String::isNotEmpty)
        if (date != null && !IsoDate.isValid(date)) return OrderResult.Failure(OrderError.REJECTED)
        return fulfillment.darkKitchenAvailability(zipCode, date)
    }

    /** The grocery providers there are. */
    suspend fun groceryProviders(): OrderResult<List<FulfillmentProvider>> = fulfillment.groceryProviders()

    /** The grocery providers that can supply [items] for delivery to [zipCode]. */
    suspend fun searchGrocery(
        items: List<GrocerySearchItem>,
        zipCode: String,
        providers: List<String> = emptyList(),
    ): OrderResult<List<FulfillmentProvider>> = fulfillment.searchGrocery(items, zipCode, providers)

    // --- orders ---

    /** The user's orders, cache-first then refreshed; only those with [status] when given. */
    fun orders(status: String? = null): Flow<OrderResult<Fetched<List<Order>>>> = orders.orders(status)

    /** One of the user's orders, cache-first then refreshed. */
    fun order(orderId: String): Flow<OrderResult<Fetched<Order>>> = orders.order(orderId)

    /**
     * Cancel an order; a paid one is refunded in full unless [refundAmount] (positive, at most the
     * total) asks for part of it.
     */
    suspend fun cancelOrder(orderId: String, refundAmount: Double? = null): OrderResult<Order> {
        if (orderId.isBlank() || (refundAmount != null && refundAmount <= 0.0)) return OrderResult.Failure(OrderError.REJECTED)
        return orders.cancelOrder(orderId.trim(), refundAmount)
    }

    /** Pull a grocery order's latest status from its provider. */
    suspend fun syncGroceryOrder(orderId: String): OrderResult<Order> {
        if (orderId.isBlank()) return OrderResult.Failure(OrderError.REJECTED)
        return orders.syncGroceryOrder(orderId.trim())
    }

    /** What the user still has to do to pay [order] (an OXXO voucher, a SPEI transfer, a PayPal approval). */
    fun paymentInstructions(order: Order): PaymentInstructions = order.paymentInstructions()

    // --- saved payment methods ---

    /** The user's saved payment methods. */
    suspend fun paymentMethods(): OrderResult<List<PaymentMethod>> = payments.paymentMethods()

    /** Save a tokenized payment method for the next checkout. */
    suspend fun addPaymentMethod(method: NewPaymentMethod): OrderResult<PaymentMethod> = payments.addPaymentMethod(method)

    /** Delete a saved payment method. */
    suspend fun deletePaymentMethod(paymentMethodId: String): OrderResult<Unit> =
        payments.deletePaymentMethod(paymentMethodId)
}

private const val KEY_BYTES = 16

/** A fresh, unguessable idempotency key: 128 random bits as hex. */
internal fun randomIdempotencyKey(): String =
    Random.nextBytes(KEY_BYTES).joinToString("") { byte -> (byte.toInt() and 0xFF).toString(16).padStart(2, '0') }
