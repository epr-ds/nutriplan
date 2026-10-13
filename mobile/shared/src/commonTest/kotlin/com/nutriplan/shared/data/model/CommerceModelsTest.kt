package com.nutriplan.shared.data.model

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class CommerceModelsTest {

    @Test
    fun `CreateOrderRequest creates correctly`() {
        val request = CreateOrderRequest(
            items = listOf(OrderItem(recipeId = "recipe-1", recipeName = "Salad", quantity = 2, unitPrice = 9.5)),
            paymentMethodId = "pm-456",
            shippingAddress = Address(
                line1 = "123 Main St",
                city = "Mexico City",
                state = "CDMX",
                postalCode = "01000",
                country = "MX",
            ),
        )
        assertEquals(1, request.items.size)
        assertEquals(2, request.items.first().quantity)
        assertEquals("pm-456", request.paymentMethodId)
        assertEquals("123 Main St", request.shippingAddress?.line1)
        assertNull(request.notes)
    }

    @Test
    fun `CancelOrderRequest creates correctly`() {
        val request = CancelOrderRequest(reason = "Changed my mind")
        assertEquals("Changed my mind", request.reason)
    }

    @Test
    fun `OrderQuery creates correctly`() {
        val query = OrderQuery(status = "pending", limit = 10, offset = 0)
        assertEquals("pending", query.status)
        assertEquals(10, query.limit)
        assertEquals(0, query.offset)
    }

    @Test
    fun `SyncGroceryRequest creates correctly`() {
        val request = SyncGroceryRequest(
            items = listOf(
                GroceryItem(name = "milk", quantity = 1.0, unit = "l"),
                GroceryItem(name = "eggs", quantity = 12.0, unit = "unit", aisle = "dairy"),
            ),
        )
        assertEquals(2, request.items.size)
        assertEquals("milk", request.items[0].name)
        assertEquals("dairy", request.items[1].aisle)
    }

    @Test
    fun `CreatePaymentMethodRequest creates correctly`() {
        val request = CreatePaymentMethodRequest(type = "card", token = "tok_123", isDefault = true)
        assertEquals("card", request.type)
        assertEquals("tok_123", request.token)
        assertEquals(true, request.isDefault)
    }

    @Test
    fun `Order creates correctly`() {
        val order = Order(
            id = "order-123",
            userId = "user-1",
            items = emptyList(),
            status = "pending",
            subtotal = 90.0,
            tax = 9.99,
            total = 99.99,
        )
        assertEquals("order-123", order.id)
        assertEquals("pending", order.status)
        assertEquals(99.99, order.total)
        assertNull(order.shippingAddress)
    }

    @Test
    fun `PaymentMethod creates correctly`() {
        val paymentMethod = PaymentMethod(id = "pm-123", type = "card", lastFour = "4242", isDefault = true)
        assertEquals("pm-123", paymentMethod.id)
        assertEquals("4242", paymentMethod.lastFour)
        assertEquals(true, paymentMethod.isDefault)
    }
}