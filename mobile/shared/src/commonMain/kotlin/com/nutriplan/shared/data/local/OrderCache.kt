package com.nutriplan.shared.data.local

import com.nutriplan.db.NutriPlanDatabase
import com.nutriplan.shared.data.model.Order
import kotlinx.serialization.json.Json

/**
 * Where the order repository keeps its offline copy of the user's orders (COM-504): [OrderCache] on
 * the device, an in-memory map in tests.
 */
interface OrderStore {
    /** The stored orders, newest first; only those with [status] when given. */
    fun getOrders(status: String? = null): List<Order>

    /** One stored order, or null. */
    fun getOrder(orderId: String): Order?

    /** Replace everything with [orders] (the server's full list, newest first). */
    fun replaceAll(orders: List<Order>)

    /** Refresh one order in place; a new one goes in front. */
    fun upsert(order: Order)

    /** Forget one order. */
    fun remove(orderId: String)
}

/**
 * On-device copy of the user's orders (COM-503), so orders can be shown when the Commerce service
 * cannot be reached. It holds exactly what the server last sent, in the server's order (newest
 * first): a full list refresh replaces it ([replaceAll]), and any single order the server returns --
 * a detail read, a new order, a cancellation, a grocery sync -- refreshes that order in place
 * ([upsert]).
 */
class OrderCache(private val database: NutriPlanDatabase) : OrderStore {

    private val queries = database.cachedOrderQueries

    /** Tolerant on read: a cached blob written by an older app version must never crash the app. */
    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    /** The cached orders, newest first; only those with [status] when given. Unreadable rows are skipped. */
    override fun getOrders(status: String?): List<Order> {
        val rows = if (status == null) queries.selectAll() else queries.selectByStatus(status)
        return rows.executeAsList().mapNotNull(::decode)
    }

    /** One cached order, or null when it is not cached (or cannot be read). */
    override fun getOrder(orderId: String): Order? = queries.selectById(orderId).executeAsOneOrNull()?.let(::decode)

    /** Replace everything with [orders] (the server's full list, newest first) atomically. */
    override fun replaceAll(orders: List<Order>) {
        database.transaction {
            queries.deleteAll()
            orders.forEachIndexed { position, order -> insert(order, position.toLong()) }
        }
    }

    /**
     * Refresh one order with what the server just returned. An order already cached keeps its place
     * in the list; a new one (just created) goes in front, where the server lists it too.
     */
    override fun upsert(order: Order) {
        database.transaction {
            val position = queries.selectPosition(order.id).executeAsOneOrNull()
                ?: ((queries.selectFirstPosition().executeAsOneOrNull() ?: 0L) - 1L)
            insert(order, position)
        }
    }

    /** Forget one order (for example when the server no longer has it). */
    override fun remove(orderId: String) {
        queries.deleteOrder(orderId)
    }

    /** Forget every order (for example on sign-out). */
    fun clear() {
        queries.deleteAll()
    }

    private fun insert(order: Order, position: Long) {
        queries.insertOrder(
            order_id = order.id,
            position = position,
            status = order.status,
            order_json = json.encodeToString(Order.serializer(), order),
        )
    }

    private fun decode(text: String): Order? =
        runCatching { json.decodeFromString(Order.serializer(), text) }.getOrNull()
}
