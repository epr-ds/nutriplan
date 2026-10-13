package com.nutriplan.shared.data.model

import kotlinx.serialization.Serializable

/** Delivery address for an order. */
@Serializable
data class DeliveryAddress(
    val street: String,
    val city: String,
    val state: String,
    val postalCode: String,
    val country: String = "MX",
)

/** Payment method input for order creation. */
@Serializable
data class PaymentMethodInput(
    val type: String,
    val token: String,
)

/** Order response. */
@Serializable
data class OrderResponse(
    val id: String,
    val status: String,
    val mealPlanId: String,
    val fulfillmentType: String,
    val deliveryAddress: DeliveryAddress?,
    val deliveryDate: String?,
    val deliveryTimeSlot: String?,
    val providerId: String?,
    val groceryOrder: GroceryOrderInfo?,
    val paymentInfo: PaymentInfo?,
    val total: OrderTotal?,
    val notes: String?,
    val createdAt: String,
    val updatedAt: String,
)

/** Grocery order info. */
@Serializable
data class GroceryOrderInfo(
    val provider: String,
    val providerOrderId: String,
    val status: String,
    val items: List<GroceryItem>,
    val total: Double,
)

/** Payment info for an order. */
@Serializable
data class PaymentInfo(
    val methodType: String,
    val status: String,
    val voucher: PaymentVoucher?,
)

/** Payment voucher (OXXO/SPEI/PayPal). */
@Serializable
data class PaymentVoucher(
    val type: String,
    val url: String?,
    val reference: String?,
    val expiresAt: String?,
    val instructions: String?,
)

/** Order total breakdown. */
@Serializable
data class OrderTotal(
    val subtotal: Double,
    val deliveryFee: Double,
    val tax: Double,
    val discount: Double,
    val total: Double,
)

/** Order list query parameters. */
data class OrderListQuery(
    val status: String? = null,
    val fromDate: String? = null,
    val page: Int = 1,
    val limit: Int = 20,
)

/** Saved payment method response. */
@Serializable
data class PaymentMethodResponse(
    val id: String,
    val type: String,
    val brand: String?,
    val last4: String?,
    val expMonth: Int?,
    val expYear: Int?,
    val isDefault: Boolean,
    val createdAt: String,
)

/** Save payment method request. */
@Serializable
data class SavePaymentMethodRequest(
    val type: String,
    val token: String,
    val brand: String?,
    val last4: String?,
    val expMonth: Int?,
    val expYear: Int?,
)
