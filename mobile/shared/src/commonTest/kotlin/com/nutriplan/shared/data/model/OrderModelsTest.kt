package com.nutriplan.shared.data.model

import kotlin.test.Test
import kotlin.test.assertEquals

class OrderModelsTest {

    @Test
    fun `Order creates correctly`() {
        val order = Order(
            id = "order-123",
            mealPlanId = "plan-456",
            status = "pending",
            totalAmount = 99.99,
            currency = "USD",
            createdAt = "2024-01-15T10:00:00Z",
            deliveryDate = "2024-01-22T00:00:00Z"
        )
        assertEquals("order-123", order.id)
        assertEquals("plan-456", order.mealPlanId)
        assertEquals("pending", order.status)
        assertEquals(99.99, order.totalAmount)
        assertEquals("USD", order.currency)
        assertEquals("2024-01-15T10:00:00Z", order.createdAt)
        assertEquals("2024-01-22T00:00:00Z", order.deliveryDate)
    }

    @Test
    fun `PaymentMethod creates correctly`() {
        val paymentMethod = PaymentMethod(
            id = "pm-123",
            type = "credit_card",
            lastFourDigits = "4242",
            expiryMonth = 12,
            expiryYear = 2027,
            isDefault = true
        )
        assertEquals("pm-123", paymentMethod.id)
        assertEquals("credit_card", paymentMethod.type)
        assertEquals("4242", paymentMethod.lastFourDigits)
        assertEquals(12, paymentMethod.expiryMonth)
        assertEquals(2027, paymentMethod.expiryYear)
        assertEquals(true, paymentMethod.isDefault)
    }
}
