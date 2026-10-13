++ b/mobile/shared/src/commonMain/kotlin/com/nutriplan/shared/data/model/CommerceModels.kt
package com.nutriplan.shared.data.model

import kotlinx.serialization.Serializable

/** Request to create an order. */
@Serializable
data class CreateOrderRequest(
    val items: List<OrderItem>,
    val paymentMethodId: String,
    val shippingAddress: Address? = null,
    val notes: String? = null,
)

/** An item within an order. */
@Serializable
data class OrderItem(
    val recipeId: String,
    val recipeName: String,
    val quantity: Int,
    val unitPrice: Double,
    val mealType: String? = null,
    val scheduledDate: String? = null,
)

/** Shipping/delivery address. */
@Serializable
data class Address(
    val line1: String,
    val line2: String? = null,
    val city: String,
    val state: String,
    val postalCode: String,
    val country: String,
)

/** Order entity. */
@Serializable
data class Order(
    val id: String,
    val userId: String,
    val items: List<OrderItem>,
    val status: String,
    val subtotal: Double,
    val tax: Double,
    val total: Double,
    val paymentMethodId: String? = null,
    val shippingAddress: Address? = null,
    val createdAt: String? = null,
    val updatedAt: String? = null,
)

/** Query parameters for listing orders. */
data class OrderQuery(
    val status: String? = null,
    val limit: Int? = null,
    val offset: Int? = null,
)

/** Request to cancel an order. */
@Serializable
data class CancelOrderRequest(
    val reason: String? = null,
)

/** Request to sync grocery list for an order. */
@Serializable
data class SyncGroceryRequest(
    val items: List<GroceryItem>,
)

/** A grocery item. */
@Serializable
data class GroceryItem(
    val name: String,
    val quantity: Double,
    val unit: String,
    val aisle: String? = null,
)

/** Payment method entity. */
@Serializable
data class PaymentMethod(
    val id: String,
    val type: String,
    val lastFour: String? = null,
    val expiryMonth: Int? = null,
    val expiryYear: Int? = null,
    val isDefault: Boolean,
    val createdAt: String? = null,
)

/** Request to add a payment method. */
@Serializable
data class CreatePaymentMethodRequest(
    val type: String,
    val token: String,
    val isDefault: Boolean? = null,
)
