package com.nutriplan.shared.data.local

import com.nutriplan.shared.data.model.Money
import com.nutriplan.shared.data.model.Order
import com.nutriplan.shared.data.model.OrderItem
import com.nutriplan.shared.data.model.PaymentVoucher
import com.nutriplan.shared.testing.newDatabase
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/** COM-503: the orders the server last sent can be read back offline, in the server's order. */
class OrderCacheTest {

    private val database = newDatabase()
    private val cache = OrderCache(database)

    private fun order(id: String, status: String = "pending", total: Double = 208.0) = Order(
        id = id,
        status = status,
        fulfillmentType = "dark_kitchen",
        items = listOf(OrderItem(name = "Lentil soup", quantity = 2.0, lineTotal = Money(178.0, formatted = "$178.00"))),
        total = Money(total, formatted = "$%.2f".format(total)),
    )

    @Test
    fun `an empty cache has no orders`() {
        assertEquals(emptyList(), cache.getOrders())
        assertNull(cache.getOrder("o1"))
    }

    @Test
    fun `a full refresh is read back in the server's order with every field`() {
        val voucher = order("o2").copy(voucher = PaymentVoucher(reference = "9300 1234", amount = Money(208.0)))
        cache.replaceAll(listOf(order("o3"), voucher, order("o1")))

        assertEquals(listOf("o3", "o2", "o1"), cache.getOrders().map { it.id })
        assertEquals(voucher, cache.getOrder("o2"))
    }

    @Test
    fun `a full refresh drops orders the server no longer lists`() {
        cache.replaceAll(listOf(order("o2"), order("o1")))

        cache.replaceAll(listOf(order("o3")))

        assertEquals(listOf("o3"), cache.getOrders().map { it.id })
        assertNull(cache.getOrder("o1"))
    }

    @Test
    fun `orders can be read by status`() {
        cache.replaceAll(listOf(order("o3", "delivered"), order("o2", "pending"), order("o1", "delivered")))

        assertEquals(listOf("o3", "o1"), cache.getOrders(status = "delivered").map { it.id })
        assertEquals(listOf("o2"), cache.getOrders(status = "pending").map { it.id })
        assertEquals(emptyList(), cache.getOrders(status = "cancelled"))
    }

    @Test
    fun `refreshing a cached order updates it in place`() {
        cache.replaceAll(listOf(order("o3"), order("o2"), order("o1")))

        cache.upsert(order("o2", status = "cancelled"))

        assertEquals(listOf("o3", "o2", "o1"), cache.getOrders().map { it.id })
        assertEquals("cancelled", cache.getOrder("o2")?.status)
        assertEquals(listOf("o2"), cache.getOrders(status = "cancelled").map { it.id })
    }

    @Test
    fun `a new order goes in front, where the server lists it`() {
        cache.replaceAll(listOf(order("o2"), order("o1")))

        cache.upsert(order("o3"))
        cache.upsert(order("o4"))

        assertEquals(listOf("o4", "o3", "o2", "o1"), cache.getOrders().map { it.id })
    }

    @Test
    fun `an order can be added to an empty cache`() {
        cache.upsert(order("o1"))

        assertEquals(listOf("o1"), cache.getOrders().map { it.id })
    }

    @Test
    fun `orders survive a restart of the app`() {
        cache.replaceAll(listOf(order("o2"), order("o1")))

        // A new cache over the same database, as after the app is reopened offline.
        val reopened = OrderCache(database)

        assertEquals(listOf("o2", "o1"), reopened.getOrders().map { it.id })
    }

    @Test
    fun `an order can be forgotten, and so can all of them`() {
        cache.replaceAll(listOf(order("o2"), order("o1")))

        cache.remove("o2")
        assertEquals(listOf("o1"), cache.getOrders().map { it.id })

        cache.clear()
        assertEquals(emptyList(), cache.getOrders())
    }

    @Test
    fun `a row that cannot be read is skipped, not a crash`() {
        cache.replaceAll(listOf(order("o1")))
        database.cachedOrderQueries.insertOrder(order_id = "broken", position = -1, status = "pending", order_json = "{not json")

        assertEquals(listOf("o1"), cache.getOrders().map { it.id })
        assertNull(cache.getOrder("broken"))
    }
}
