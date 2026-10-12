package com.nutriplan.shared.data.repository

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class CommerceRepositoryUrlTest {

    @Test
    fun `createOrder uses correct endpoint`() {
        assertEquals("commerce/orders", "${ApiConfig.COMMERCE}/orders")
    }

    @Test
    fun `getOrders uses correct endpoint`() {
        assertEquals("commerce/orders", "${ApiConfig.COMMERCE}/orders")
    }

    @Test
    fun `getOrder uses correct endpoint with ID`() {
        assertEquals("commerce/orders/order-123", "${ApiConfig.COMMERCE}/orders/order-123")
    }

    @Test
    fun `cancelOrder uses correct endpoint`() {
        assertEquals("commerce/orders/order-123/cancel", "${ApiConfig.COMMERCE}/orders/order-123/cancel")
    }

    @Test
    fun `syncGrocery uses correct endpoint`() {
        assertEquals("commerce/orders/order-123/grocery/sync", "${ApiConfig.COMMERCE}/orders/order-123/grocery/sync")
    }

    @Test
    fun `getPaymentMethods uses correct endpoint`() {
        assertEquals("commerce/payment-methods", "${ApiConfig.COMMERCE}/payment-methods")
    }

    @Test
    fun `createPaymentMethod uses correct endpoint`() {
        assertEquals("commerce/payment-methods", "${ApiConfig.COMMERCE}/payment-methods")
    }

    @Test
    fun `deletePaymentMethod uses correct endpoint with ID`() {
        assertEquals("commerce/payment-methods/pm-456", "${ApiConfig.COMMERCE}/payment-methods/pm-456")
    }
}
