@file:OptIn(ExperimentalSerializationApi::class)

package com.nutriplan.shared.data.model

import kotlinx.serialization.EncodeDefault
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.Serializable

/*
 * Commerce models (COM-501), aligned with contracts/commerce.openapi.yaml, the source of truth the
 * Commerce service is verified against: orders, saved payment methods and fulfillment (dark kitchen
 * and grocery). Optional request fields the user did not set are left out of the JSON altogether
 * (never sent as null). Money is always a `MoneyResponse` ([Money]): an amount, its currency (MXN by
 * default) and the server-formatted text the UI should show. The payment webhooks in the same
 * document are server-to-server, so the app has no models for them.
 */

// --- requests ---

/** Body of `POST /orders` (`CreateOrderRequest`): an order for one meal plan. */
@Serializable
data class CreateOrderRequest(
    val mealPlanId: String,
    /** `dark_kitchen`, `grocery_delivery` or `pickup`. */
    val fulfillmentType: String,
    /** The grocery provider (e.g. `freshbasket`); required for `grocery_delivery`. */
    @EncodeDefault(EncodeDefault.Mode.NEVER) val providerId: String? = null,
    val deliveryAddress: OrderAddress,
    /** ISO date, e.g. `2026-11-02`. */
    val deliveryDate: String,
    val deliveryTimeSlot: String,
    @EncodeDefault(EncodeDefault.Mode.NEVER) val paymentMethod: PaymentMethodRequest? = null,
    @EncodeDefault(EncodeDefault.Mode.NEVER) val notes: String? = null,
)

/** Where an order is delivered (`AddressRequest`). */
@Serializable
data class OrderAddress(
    val street: String,
    @EncodeDefault(EncodeDefault.Mode.NEVER) val apartment: String? = null,
    val city: String,
    val state: String,
    val zipCode: String,
    val country: String,
    /** Notes for the courier, e.g. "ring twice". */
    @EncodeDefault(EncodeDefault.Mode.NEVER) val instructions: String? = null,
)

/**
 * How an order is paid (`PaymentMethodRequest`): a [type] and the provider [token] produced by
 * on-device tokenization. A card number or CVV is never sent.
 */
@Serializable
data class PaymentMethodRequest(
    /** `credit_card`, `debit_card`, `paypal`, `oxxo` or `spei`. */
    val type: String,
    val token: String,
)

/** Body of `POST /orders/quote` (`OrderQuoteRequest`, COM-605): what to price. */
@Serializable
data class OrderQuoteRequest(
    val mealPlanId: String,
    /** `dark_kitchen`, `grocery_delivery` or `pickup`. */
    val fulfillmentType: String,
    /** Required for `grocery_delivery`. */
    @EncodeDefault(EncodeDefault.Mode.NEVER) val providerId: String? = null,
)

/**
 * Optional body of `POST /orders/{orderId}/cancel` (`CancelOrderRequest`). Without [refundAmount] a
 * paid order is refunded in full.
 */
@Serializable
data class CancelOrderRequest(
    @EncodeDefault(EncodeDefault.Mode.NEVER) val refundAmount: Double? = null,
)

/**
 * Body of `POST /payment-methods` (`SavePaymentMethodRequest`): a tokenized instrument to reuse at
 * checkout, with optional display metadata (cards carry it, wallets do not).
 */
@Serializable
data class SavePaymentMethodRequest(
    /** `credit_card`, `debit_card`, `paypal`, `oxxo` or `spei`. */
    val type: String,
    val token: String,
    @EncodeDefault(EncodeDefault.Mode.NEVER) val brand: String? = null,
    @EncodeDefault(EncodeDefault.Mode.NEVER) val last4: String? = null,
    @EncodeDefault(EncodeDefault.Mode.NEVER) val expMonth: Int? = null,
    @EncodeDefault(EncodeDefault.Mode.NEVER) val expYear: Int? = null,
)

/** Body of `POST /fulfillment/grocery/search` (`GrocerySearchRequest`). */
@Serializable
data class GrocerySearchRequest(
    val items: List<GrocerySearchItem>,
    /** Limit the search to these providers; every provider when left out. */
    @EncodeDefault(EncodeDefault.Mode.NEVER) val providers: List<String>? = null,
    val zipCode: String,
)

/** One ingredient to look for in a grocery search. */
@Serializable
data class GrocerySearchItem(
    @EncodeDefault(EncodeDefault.Mode.NEVER) val ingredient: String? = null,
    @EncodeDefault(EncodeDefault.Mode.NEVER) val quantity: Double? = null,
    @EncodeDefault(EncodeDefault.Mode.NEVER) val unit: String? = null,
)

/** Filters for `GET /orders`; sent as query parameters, unset ones left out. */
data class OrderListQuery(
    /** `pending`, `confirmed`, `preparing`, `in_transit`, `delivered` or `cancelled`. */
    val status: String? = null,
    /** ISO date: only orders from this day on. */
    val fromDate: String? = null,
    /** 1-based; the server's default is 1. */
    val page: Int? = null,
    /** 1 to 100; the server's default is 20. */
    val limit: Int? = null,
)

// --- responses ---

/** An order (`OrderResponse`), as returned by every order operation. */
@Serializable
data class Order(
    val id: String,
    /** `pending`, `confirmed`, `preparing`, `in_transit`, `delivered` or `cancelled`. */
    val status: String? = null,
    /** `dark_kitchen`, `grocery_delivery` or `pickup`. */
    val fulfillmentType: String? = null,
    val provider: FulfillmentProvider? = null,
    val items: List<OrderItem> = emptyList(),
    val subtotal: Money? = null,
    val deliveryFee: Money? = null,
    val total: Money? = null,
    /** ISO date-time. */
    val estimatedDelivery: String? = null,
    val trackingUrl: String? = null,
    /** OXXO voucher to pay, while an OXXO order is pending. */
    val voucher: PaymentVoucher? = null,
    /** SPEI transfer instructions, while a SPEI order is pending. */
    val transfer: BankTransfer? = null,
    /** PayPal approval redirect, while a PayPal order is pending. */
    val approval: PaymentApproval? = null,
    /** The refund, once a paid order was cancelled and refunded. */
    val refund: Refund? = null,
    /** The order placed with a grocery provider, once it was placed. */
    val groceryOrder: GroceryOrder? = null,
)

/** What an order would cost (`OrderQuoteResponse`, COM-605), priced like the order itself. */
@Serializable
data class OrderQuote(
    val items: List<OrderItem> = emptyList(),
    val subtotal: Money? = null,
    val deliveryFee: Money? = null,
    val total: Money? = null,
)

/** One line of an order (`OrderItemResponse`). */
@Serializable
data class OrderItem(
    val name: String? = null,
    val quantity: Double? = null,
    val unit: String? = null,
    val unitPrice: Money? = null,
    val lineTotal: Money? = null,
)

/** An amount of money (`MoneyResponse`); show [formatted] when present. */
@Serializable
data class Money(
    val amount: Double? = null,
    val currency: String = "MXN",
    val formatted: String? = null,
)

/** An offline OXXO voucher (`VoucherResponse`): pay [amount] with [reference] before [expiresAt]. */
@Serializable
data class PaymentVoucher(
    val reference: String? = null,
    val amount: Money? = null,
    val expiresAt: String? = null,
    val provider: String? = null,
    val barcodeUrl: String? = null,
)

/** SPEI bank-transfer instructions (`TransferResponse`): transfer [amount] to [clabe] quoting [reference]. */
@Serializable
data class BankTransfer(
    val clabe: String? = null,
    val reference: String? = null,
    val amount: Money? = null,
    val expiresAt: String? = null,
    val provider: String? = null,
)

/** A PayPal approval (`ApprovalResponse`): send the user to [approvalUrl] before [expiresAt]. */
@Serializable
data class PaymentApproval(
    val approvalUrl: String? = null,
    val reference: String? = null,
    val amount: Money? = null,
    val expiresAt: String? = null,
    val provider: String? = null,
)

/** A refund of a cancelled, paid order (`RefundResponse`). */
@Serializable
data class Refund(
    val refundId: String? = null,
    /** `full` or `partial`. */
    val status: String? = null,
    val amount: Money? = null,
    val provider: String? = null,
)

/** The order placed with a grocery provider (`GroceryOrderResponse`). */
@Serializable
data class GroceryOrder(
    val providerId: String? = null,
    val externalOrderId: String? = null,
    /**
     * `pending`, `confirmed`, `preparing`, `out_for_delivery`, `delivered`, `cancelled`, `failed` or
     * `unknown`.
     */
    val status: String? = null,
)

/** A saved payment method (`PaymentMethodResponse`): display metadata only, never the token. */
@Serializable
data class PaymentMethod(
    val id: String,
    /** `credit_card`, `debit_card`, `paypal`, `oxxo` or `spei`. */
    val type: String? = null,
    val brand: String? = null,
    val last4: String? = null,
    val expMonth: Int? = null,
    val expYear: Int? = null,
    /** ISO date-time. */
    val createdAt: String? = null,
)

/** Whether a dark kitchen delivers to a zip code, and when (`AvailabilityResponse`). */
@Serializable
data class KitchenAvailability(
    val available: Boolean = false,
    val zipCode: String? = null,
    val timeSlots: List<String> = emptyList(),
)

/** A dark kitchen or grocery provider (`ProviderResponse`). */
@Serializable
data class FulfillmentProvider(
    val id: String? = null,
    val name: String? = null,
    /** `dark_kitchen` or `grocery`. */
    val type: String? = null,
    val logoUrl: String? = null,
    val estimatedDelivery: String? = null,
)
