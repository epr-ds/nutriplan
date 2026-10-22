package com.nutriplan.shared.data.local

import com.nutriplan.db.NutriPlanDatabase
import com.nutriplan.shared.data.model.Order
import kotlinx.serialization.json.Json

/**
 * On-device copy of the user's orders (COM-503), so orders can be shown when the Commerce service
 * cannot be reached. It holds exactly what the server last sent, in the server's order (newest
 * first): a full list refresh replaces it ([replaceAll]), and any single order the server returns --
 * a detail read, a new order, a cancellation, a grocery sync -- refreshes that order in place
 * ([upsert]).
 */
class OrderCache(private val database: NutriPlanDatabase) {

    private val queries = database.cachedOrderQueries

    /** Tolerant on read: a cached blob written by an older app version must never crash the app. */
    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    /** The cached orders, newest first; only those with [status] when given. Unreadable rows are skipped. */
    fun getOrders(status: String? = null): List<Order> {
        val rows = if (status == null) queries.selectAll() else queries.selectByStatus(status)
        return rows.executeAsList().mapNotNull(::decode)
    }

    /** One cached order, or null when it is not cached (or cannot be read). */
    fun getOrder(orderId: String): Order? = queries.selectById(orderId).executeAsOneOrNull()?.let(::decode)

    /** Replace everything with [orders] (the server's full list, newest first) atomically. */
    fun replaceAll(orders: List<Order>) {
        database.transaction {
            queries.deleteAll()
            orders.forEachIndexed { position, order -> insert(order, position.toLong()) }
        }
    }

    /**
     * Refresh one order with what the server just returned. An order already cached keeps its place
     * in the list; a new one (just created) goes in front, where the server lists it too.
     */
    fun upsert(order: Order) {
        database.transaction {
            val position = queries.selectPosition(order.id).executeAsOneOrNull()
                ?: ((queries.selectFirstPosition().executeAsOneOrNull() ?: 0L) - 1L)
            insert(order, position)
        }
    }

    /** Forget one order (for example when the server no longer has it). */
    fun remove(orderId: String) {
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
