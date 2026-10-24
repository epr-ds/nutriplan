package com.nutriplan.shared.contract

/**
 * A minimal, machine-checkable projection of `contracts/commerce.openapi.yaml` (COM-803).
 *
 * This is what the spec-derived mock ([SpecDerivedCommerceMock]) serves: every documented Commerce
 * operation the app's client calls, with its request/response schemas, success status, query and
 * header parameters, and the request schemas' enum values, nested objects and array items.
 * `scripts/check_mobile_commerce_contract.py` parses this file, the OpenAPI document and the client
 * models, and fails CI if any of the three drifts from the others.
 *
 * The payment and kitchen webhooks in the same document are called by providers, not the app, so
 * they are left out.
 */
internal object CommerceContract {

    /** The gateway route + API version prefix that fronts the Commerce service. */
    const val clientPrefix: String = "/commerce/v1"

    /**
     * A documented operation: method + service-relative path, the schemas of its body and of its
     * success response ([list] when the response is an array of [response]), its success status, its
     * query parameters ([requiredQuery] the ones it cannot do without, [queryEnums] their allowed
     * values), the header parameters it documents, and whether a body is required when it takes one.
     */
    data class Operation(
        val method: String,
        val path: String,
        val request: String?,
        val response: String?,
        val status: Int,
        val list: Boolean = false,
        val query: Set<String> = emptySet(),
        val requiredQuery: Set<String> = emptySet(),
        val queryEnums: Map<String, Set<String>> = emptyMap(),
        val headers: Set<String> = emptySet(),
        val bodyRequired: Boolean = true,
    )

    /**
     * A schema's required and allowed property names (camelCase, as on the wire), the allowed values
     * of its enum properties, the schema of its nested object properties, and the schema of the items
     * of its array-of-object properties (an inline item schema is named `Schema.property`).
     */
    data class Schema(
        val required: Set<String>,
        val properties: Set<String>,
        val enums: Map<String, Set<String>> = emptyMap(),
        val nested: Map<String, String> = emptyMap(),
        val arrays: Map<String, String> = emptyMap(),
    )

    val operations: List<Operation> = listOf(
        Operation(
            "POST",
            "/orders",
            request = "CreateOrderRequest",
            response = "OrderResponse",
            status = 201,
            headers = setOf("Idempotency-Key"),
        ),
        Operation(
            "GET",
            "/orders",
            request = null,
            response = "OrderResponse",
            status = 200,
            list = true,
            query = setOf("status", "fromDate", "page", "limit"),
            queryEnums = mapOf("status" to setOf("pending", "confirmed", "preparing", "in_transit", "delivered", "cancelled")),
        ),
        Operation("POST", "/orders/quote", request = "OrderQuoteRequest", response = "OrderQuoteResponse", status = 200),
        Operation("GET", "/orders/{orderId}", request = null, response = "OrderResponse", status = 200),
        Operation(
            "POST",
            "/orders/{orderId}/cancel",
            request = "CancelOrderRequest",
            response = "OrderResponse",
            status = 200,
            bodyRequired = false,
        ),
        Operation("POST", "/orders/{orderId}/grocery/sync", request = null, response = "OrderResponse", status = 200),
        Operation("GET", "/payment-methods", request = null, response = "PaymentMethodResponse", status = 200, list = true),
        Operation(
            "POST",
            "/payment-methods",
            request = "SavePaymentMethodRequest",
            response = "PaymentMethodResponse",
            status = 201,
        ),
        Operation("DELETE", "/payment-methods/{paymentMethodId}", request = null, response = null, status = 204),
        Operation(
            "GET",
            "/fulfillment/dark-kitchen/availability",
            request = null,
            response = "AvailabilityResponse",
            status = 200,
            query = setOf("zipCode", "deliveryDate"),
            requiredQuery = setOf("zipCode"),
        ),
        Operation(
            "POST",
            "/fulfillment/grocery/search",
            request = "GrocerySearchRequest",
            response = "ProviderResponse",
            status = 200,
            list = true,
        ),
        Operation(
            "GET",
            "/fulfillment/grocery/providers",
            request = null,
            response = "ProviderResponse",
            status = 200,
            list = true,
        ),
    )

    val schemas: Map<String, Schema> = mapOf(
        "CreateOrderRequest" to Schema(
            required = setOf("mealPlanId", "fulfillmentType", "deliveryAddress", "deliveryDate", "deliveryTimeSlot"),
            properties = setOf(
                "mealPlanId",
                "fulfillmentType",
                "providerId",
                "deliveryAddress",
                "deliveryDate",
                "deliveryTimeSlot",
                "paymentMethod",
                "notes",
            ),
            enums = mapOf("fulfillmentType" to setOf("dark_kitchen", "grocery_delivery", "pickup")),
            nested = mapOf("deliveryAddress" to "AddressRequest", "paymentMethod" to "PaymentMethodRequest"),
        ),
        "AddressRequest" to Schema(
            required = setOf("street", "city", "state", "zipCode", "country"),
            properties = setOf("street", "apartment", "city", "state", "zipCode", "country", "instructions"),
        ),
        "PaymentMethodRequest" to Schema(
            required = setOf("type"),
            properties = setOf("type", "token"),
            enums = mapOf("type" to setOf("credit_card", "debit_card", "paypal", "oxxo", "spei")),
        ),
        "OrderQuoteRequest" to Schema(
            required = setOf("mealPlanId", "fulfillmentType"),
            properties = setOf("mealPlanId", "fulfillmentType", "providerId"),
            enums = mapOf("fulfillmentType" to setOf("dark_kitchen", "grocery_delivery", "pickup")),
        ),
        "OrderQuoteResponse" to Schema(
            required = setOf("items", "subtotal", "deliveryFee", "total"),
            properties = setOf("items", "subtotal", "deliveryFee", "total"),
        ),
        "CancelOrderRequest" to Schema(
            required = emptySet(),
            properties = setOf("refundAmount"),
        ),
        "SavePaymentMethodRequest" to Schema(
            required = setOf("type", "token"),
            properties = setOf("type", "token", "brand", "last4", "expMonth", "expYear"),
            enums = mapOf("type" to setOf("credit_card", "debit_card", "paypal", "oxxo", "spei")),
        ),
        "GrocerySearchRequest" to Schema(
            required = setOf("items", "zipCode"),
            properties = setOf("items", "providers", "zipCode"),
            arrays = mapOf("items" to "GrocerySearchRequest.items"),
        ),
        "GrocerySearchRequest.items" to Schema(
            required = emptySet(),
            properties = setOf("ingredient", "quantity", "unit"),
        ),
        "OrderResponse" to Schema(
            required = emptySet(),
            properties = setOf(
                "id",
                "status",
                "fulfillmentType",
                "provider",
                "deliveryAddress",
                "deliveryDate",
                "deliveryTimeSlot",
                "createdAt",
                "items",
                "subtotal",
                "deliveryFee",
                "total",
                "estimatedDelivery",
                "trackingUrl",
                "voucher",
                "transfer",
                "approval",
                "refund",
                "groceryOrder",
            ),
        ),
        "PaymentMethodResponse" to Schema(
            required = emptySet(),
            properties = setOf("id", "type", "brand", "last4", "expMonth", "expYear", "createdAt"),
        ),
        "AvailabilityResponse" to Schema(
            required = emptySet(),
            properties = setOf("available", "zipCode", "timeSlots"),
        ),
        "ProviderResponse" to Schema(
            required = emptySet(),
            properties = setOf("id", "name", "type", "logoUrl", "estimatedDelivery"),
        ),
    )
}
