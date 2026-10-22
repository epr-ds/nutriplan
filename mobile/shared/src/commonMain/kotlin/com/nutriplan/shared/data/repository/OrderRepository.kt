package com.nutriplan.shared.data.repository

import com.nutriplan.shared.commerce.Fetched
import com.nutriplan.shared.commerce.OrderError
import com.nutriplan.shared.commerce.OrderResult
import com.nutriplan.shared.commerce.toOrderError
import com.nutriplan.shared.data.local.OrderStore
import com.nutriplan.shared.data.local.SavedAddressStore
import com.nutriplan.shared.data.model.CancelOrderRequest
import com.nutriplan.shared.data.model.CreateOrderRequest
import com.nutriplan.shared.data.model.Order
import com.nutriplan.shared.data.model.OrderListQuery
import com.nutriplan.shared.data.network.ApiFailure
import com.nutriplan.shared.data.network.toApiFailure
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlin.coroutines.cancellation.CancellationException

/**
 * The user's orders, offline-first (COM-504): the Commerce service is the source of truth and an
 * [OrderStore] (the device's [com.nutriplan.shared.data.local.OrderCache]) keeps a copy. Every
 * operation returns an [OrderResult] instead of throwing, so a screen only handles a value or an
 * [OrderError].
 *
 * - **Reads are cache-first, then refresh.** [orders] and [order] emit the device's copy at once
 *   (when there is one, marked not [Fetched.fresh]) and then the server's answer, which also
 *   refreshes the copy. When the server cannot be reached (offline or a 5xx) the copy stays, with
 *   [Fetched.refreshError] saying why; with no copy that is a [OrderResult.Failure]. A rejected
 *   session is always a failure, never answered from the copy, and a 404 forgets the cached order.
 * - **Writes go through.** [createOrder], [cancelOrder] and [syncGroceryOrder] need the server; the
 *   order it returns is stored, so lists and details show it straight away, also offline later. A
 *   created order's delivery address is saved to the [addresses] book for the next checkout.
 */
class OrderRepository(
    private val remote: CommerceRepository,
    private val store: OrderStore,
    private val addresses: SavedAddressStore? = null,
) {

    /** The user's orders, newest first; only those with [status] when given. */
    fun orders(status: String? = null): Flow<OrderResult<Fetched<List<Order>>>> = flow {
        val cached = store.getOrders(status)
        if (cached.isNotEmpty()) emit(OrderResult.Success(Fetched(cached, fresh = false)))

        val outcome = fetch { remote.listOrders(OrderListQuery(status = status, limit = PAGE_SIZE)) }
        val result = when (outcome) {
            is Outcome.Ok -> {
                refreshList(status, outcome.value)
                OrderResult.Success(Fetched(outcome.value, fresh = true))
            }
            is Outcome.Failed -> stale(cached.takeIf { it.isNotEmpty() }, outcome)
        }
        emit(result)
    }

    /** One of the user's orders. */
    fun order(orderId: String): Flow<OrderResult<Fetched<Order>>> = flow {
        val cached = store.getOrder(orderId)
        if (cached != null) emit(OrderResult.Success(Fetched(cached, fresh = false)))

        val result = when (val outcome = fetch { remote.getOrder(orderId) }) {
            is Outcome.Ok -> {
                store.upsert(outcome.value)
                OrderResult.Success(Fetched(outcome.value, fresh = true))
            }
            is Outcome.Failed -> {
                if (outcome.error == OrderError.NOT_FOUND) store.remove(orderId)
                stale(cached, outcome)
            }
        }
        emit(result)
    }

    /**
     * Place an order. Pass the same [idempotencyKey] when retrying after a failure the request may
     * have survived (a dropped connection, a timeout), so the server returns the first order instead
     * of creating -- and charging -- a second one.
     */
    suspend fun createOrder(request: CreateOrderRequest, idempotencyKey: String? = null): OrderResult<Order> {
        val result = write(orderId = null) { remote.createOrder(request, idempotencyKey) }
        if (result is OrderResult.Success) {
            // The address book is a convenience: failing to save to it never fails the order.
            runCatching { addresses?.save(request.deliveryAddress) }
        }
        return result
    }

    /** Cancel an order; a paid one is refunded in full unless [refundAmount] asks for part of it. */
    suspend fun cancelOrder(orderId: String, refundAmount: Double? = null): OrderResult<Order> =
        write(orderId) { remote.cancelOrder(orderId, refundAmount?.let { CancelOrderRequest(refundAmount = it) }) }

    /** Pull a grocery order's latest status from its provider. */
    suspend fun syncGroceryOrder(orderId: String): OrderResult<Order> =
        write(orderId) { remote.syncGroceryOrder(orderId) }

    /**
     * Refresh the copy with a list the server returned. A complete answer (fewer than a page) for
     * every status replaces the copy; for one status it drops the copied orders of that status the
     * server no longer lists. The listed orders are then stored, oldest first, so the newest ends up
     * in front.
     */
    private fun refreshList(status: String?, orders: List<Order>) {
        val complete = orders.size < PAGE_SIZE
        if (status == null && complete) {
            store.replaceAll(orders)
            return
        }
        if (complete) {
            val listed = orders.mapTo(HashSet()) { it.id }
            store.getOrders(status).filter { it.id !in listed }.forEach { store.remove(it.id) }
        }
        orders.asReversed().forEach(store::upsert)
    }

    /** The cached [copy] marked stale when the failure allows it, else the failure itself. */
    private fun <T> stale(copy: T?, failure: Outcome.Failed): OrderResult<Fetched<T>> =
        if (copy != null && failure.canShowCopy) {
            OrderResult.Success(Fetched(copy, fresh = false, refreshError = failure.error))
        } else {
            OrderResult.Failure(failure.error)
        }

    private suspend fun write(orderId: String?, call: suspend () -> Order): OrderResult<Order> =
        when (val outcome = fetch(call)) {
            is Outcome.Ok -> {
                store.upsert(outcome.value)
                OrderResult.Success(outcome.value)
            }
            is Outcome.Failed -> {
                if (orderId != null && outcome.error == OrderError.NOT_FOUND) store.remove(orderId)
                OrderResult.Failure(outcome.error)
            }
        }

    /** Run a server call, turning a failure into a value (cancellation is never swallowed). */
    private suspend fun <T> fetch(call: suspend () -> T): Outcome<T> =
        try {
            Outcome.Ok(call())
        } catch (e: CancellationException) {
            throw e
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            val failure = e.toApiFailure()
            Outcome.Failed(
                error = e.toOrderError(),
                // Only "could not reach the server" leaves the copy usable; a rejected session never does.
                canShowCopy = failure == ApiFailure.OFFLINE || failure == ApiFailure.SERVER,
            )
        }

    private sealed interface Outcome<out T> {
        data class Ok<out T>(val value: T) : Outcome<T>
        data class Failed(val error: OrderError, val canShowCopy: Boolean) : Outcome<Nothing>
    }

    private companion object {
        /** The contract's largest page for `GET /orders`. */
        const val PAGE_SIZE = 100
    }
}
