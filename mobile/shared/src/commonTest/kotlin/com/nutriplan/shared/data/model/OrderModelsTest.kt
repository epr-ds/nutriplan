package com.nutriplan.shared.data.model

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class OrderModelsTest {

    @Test
    fun `DeliveryAddress defaults country to MX`() {
        val address = DeliveryAddress(street = "Av. Reforma 1", city = "Mexico City", state = "CDMX", postalCode = "06600")
        assertEquals("MX", address.country)
    }

    @Test
    fun `OrderResponse creates correctly`() {
        val order = OrderResponse(
            id = "order-123",
            status = "pending",
            mealPlanId = "plan-456",
            fulfillmentType = "delivery",
            deliveryAddress = null,
            deliveryDate = "2024-01-22",
            deliveryTimeSlot = null,
            providerId = null,
            groceryOrder = null,
            paymentInfo = null,
            total = OrderTotal(subtotal = 90.0, deliveryFee = 5.0, tax = 4.99, discount = 0.0, total = 99.99),
            notes = null,
            createdAt = "2024-01-15T10:00:00Z",
            updatedAt = "2024-01-15T10:00:00Z",
        )
        assertEquals("order-123", order.id)
        assertEquals("plan-456", order.mealPlanId)
        assertEquals(99.99, order.total?.total)
        assertNull(order.deliveryAddress)
    }

    @Test
    fun `OrderListQuery has pagination defaults`() {
        val query = OrderListQuery()
        assertNull(query.status)
        assertEquals(1, query.page)
        assertEquals(20, query.limit)
    }

    @Test
    fun `PaymentMethodResponse creates correctly`() {
        val method = PaymentMethodResponse(
            id = "pm-123",
            type = "card",
            brand = "visa",
            last4 = "4242",
            expMonth = 12,
            expYear = 2027,
            isDefault = true,
            createdAt = "2024-01-15T10:00:00Z",
        )
        assertEquals("pm-123", method.id)
        assertEquals("4242", method.last4)
        assertEquals(12, method.expMonth)
        assertEquals(2027, method.expYear)
        assertEquals(true, method.isDefault)
    }
}