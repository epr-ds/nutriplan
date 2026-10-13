package com.nutriplan.shared.data.repository

import com.nutriplan.shared.data.ApiConfig
import kotlin.test.Test
import kotlin.test.assertEquals

class CommerceRepositoryUrlTest {

    @Test
    fun `createOrder uses correct endpoint`() {
        assertEquals("https://api.nutriplan.app/commerce/v1/orders", "${ApiConfig.COMMERCE}/orders")
    }

    @Test
    fun `getOrders uses correct endpoint`() {
        assertEquals("https://api.nutriplan.app/commerce/v1/orders", "${ApiConfig.COMMERCE}/orders")
    }

    @Test
    fun `getOrder uses correct endpoint with ID`() {
        assertEquals("https://api.nutriplan.app/commerce/v1/orders/order-123", "${ApiConfig.COMMERCE}/orders/order-123")
    }

    @Test
    fun `cancelOrder uses correct endpoint`() {
        assertEquals("https://api.nutriplan.app/commerce/v1/orders/order-123/cancel", "${ApiConfig.COMMERCE}/orders/order-123/cancel")
    }

    @Test
    fun `syncGrocery uses correct endpoint`() {
        assertEquals("https://api.nutriplan.app/commerce/v1/orders/order-123/grocery/sync", "${ApiConfig.COMMERCE}/orders/order-123/grocery/sync")
    }

    @Test
    fun `getPaymentMethods uses correct endpoint`() {
        assertEquals("https://api.nutriplan.app/commerce/v1/payment-methods", "${ApiConfig.COMMERCE}/payment-methods")
    }

    @Test
    fun `createPaymentMethod uses correct endpoint`() {
        assertEquals("https://api.nutriplan.app/commerce/v1/payment-methods", "${ApiConfig.COMMERCE}/payment-methods")
    }

    @Test
    fun `deletePaymentMethod uses correct endpoint with ID`() {
        assertEquals("https://api.nutriplan.app/commerce/v1/payment-methods/pm-456", "${ApiConfig.COMMERCE}/payment-methods/pm-456")
    }
}
