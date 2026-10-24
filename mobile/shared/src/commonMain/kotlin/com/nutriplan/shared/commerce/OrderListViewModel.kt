package com.nutriplan.shared.commerce

import com.nutriplan.shared.data.model.Order
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

/** The filters of the order list (COM-701), by order status. */
enum class OrderFilter(private val statuses: Set<String>?) {
    ALL(null),

    /** Still on its way: pending, confirmed, being prepared or in transit. */
    ACTIVE(setOf("pending", "confirmed", "preparing", "in_transit")),
    DELIVERED(setOf("delivered")),
    CANCELLED(setOf("cancelled")),
    ;

    fun matches(order: Order): Boolean = statuses == null || order.status in statuses
}

/** Observable state of the order list (COM-701). */
data class OrderListUiState(
    val isLoading: Boolean = true,
    /** Every order, newest first; [visibleOrders] is what the filter shows. */
    val orders: List<Order> = emptyList(),
    val filter: OrderFilter = OrderFilter.ALL,
    /** The orders shown are the device's copy: the server could not be reached, for this reason. */
    val refreshError: OrderError? = null,
    /** Why the orders could not be loaded at all (nothing is cached). */
    val loadError: OrderError? = null,
    /** The server rejected the session: the screen sends the user to sign in again. */
    val sessionExpired: Boolean = false,
) {
    val visibleOrders: List<Order> get() = orders.filter(filter::matches)

    /** Loaded, and the user has no orders at all. */
    val isEmpty: Boolean get() = !isLoading && loadError == null && orders.isEmpty()

    /** There are orders, just none with the chosen filter. */
    val isFilteredEmpty: Boolean get() = orders.isNotEmpty() && visibleOrders.isEmpty()

    /** How many orders [filter] would show. */
    fun count(filter: OrderFilter): Int = orders.count(filter::matches)
}

/**
 * Shared logic of the order list (COM-701), used by the Compose and SwiftUI screens: the user's
 * orders, newest first, with a filter by status and a reorder action.
 *
 * Orders are shown from the device's copy first and then refreshed from the server
 * ([CommerceUseCases.orders]); when the server cannot be reached the copy stays on screen with
 * [OrderListUiState.refreshError]. The filter works on the loaded list, so it works offline too.
 *
 * Reordering starts a new checkout with the same delivery as an earlier order (see [canReorder]);
 * the checkout reads the order itself ([CheckoutViewModel.start]).
 */
class OrderListViewModel(private val useCases: CommerceUseCases) {

    private val _state = MutableStateFlow(OrderListUiState())
    val state: StateFlow<OrderListUiState> = _state.asStateFlow()

    /** Load the orders: the device's copy first, then the server's. */
    suspend fun load() {
        _state.update { it.copy(isLoading = true) }
        useCases.orders().collect { result ->
            when (result) {
                is OrderResult.Success -> _state.update {
                    it.copy(
                        orders = result.value.value,
                        // The cached copy is followed by the server's answer; only that one ends loading.
                        isLoading = !result.value.fresh && result.value.refreshError == null,
                        refreshError = result.value.refreshError,
                        loadError = null,
                        sessionExpired = it.sessionExpired || result.value.refreshError == OrderError.SESSION_EXPIRED,
                    )
                }
                is OrderResult.Failure -> _state.update {
                    it.copy(
                        isLoading = false,
                        loadError = result.error,
                        sessionExpired = it.sessionExpired || result.error == OrderError.SESSION_EXPIRED,
                    )
                }
            }
        }
    }

    fun selectFilter(filter: OrderFilter) {
        _state.update { it.copy(filter = filter) }
    }

    /** Whether [order] can be ordered again: its fulfillment type is one the checkout offers. */
    fun canReorder(order: Order): Boolean = order.fulfillmentType in CheckoutDraft.FULFILLMENT_TYPES
}
