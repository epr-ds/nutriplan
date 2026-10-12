package com.nutriplan.shared.data.model

import kotlin.test.Test
import kotlin.test.assertEquals

class CommerceModelsTest {

    @Test
    fun `CreateOrderRequest creates correctly`() {
        val request = CreateOrderRequest(
            mealPlanId = "plan-123",
            paymentMethodId = "pm-456",
            deliveryAddress = "123 Main St"
        )
        assertEquals("plan-123", request.mealPlanId)
        assertEquals("pm-456", request.paymentMethodId)
        assertEquals("123 Main St", request.deliveryAddress)
    }

    @Test
    fun `CancelOrderRequest creates correctly`() {
        val request = CancelOrderRequest(reason = "Changed my mind")
        assertEquals("Changed my mind", request.reason)
    }

    @Test
    fun `OrderQuery creates correctly`() {
        val query = OrderQuery(
            status = "pending",
            limit = 10,
            offset = 0
        )
        assertEquals("pending", query.status)
        assertEquals(10, query.limit)
        assertEquals(0, query.offset)
    }

    @Test
    fun `SyncGroceryRequest creates correctly`() {
        val request = SyncGroceryRequest(
            items = listOf("milk", "eggs", "bread")
        )
        assertEquals(3, request.items.size)
        assertEquals("milk", request.items[0])
    }

    @Test
    fun `CreatePaymentMethodRequest creates correctly`() {
        val request = CreatePaymentMethodRequest(
            type = "credit_card",
            lastFourDigits = "4242",
            expiryMonth = 12,
            expiryYear = 2027
        )
        assertEquals("credit_card", request.type)
        assertEquals("4242", request.lastFourDigits)
        assertEquals(12, request.expiryMonth)
        assertEquals(2027, request.expiryYear)
    }
}
