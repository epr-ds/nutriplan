package com.nutriplan.shared.commerce

import com.nutriplan.shared.data.model.Order
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

/** Where a step of the status timeline stands (COM-703). */
enum class TimelineStepState { DONE, CURRENT, UPCOMING }

/** One step of an order's status timeline: a status, when it was reached (ISO date-time), and where it stands. */
data class TimelineStep(val status: String, val reachedAt: String?, val state: TimelineStepState)

/** The lifecycle an order goes through when nothing goes wrong. */
internal val ORDER_PATH = listOf("pending", "confirmed", "preparing", "in_transit", "delivered")

/** Statuses an order can still be cancelled from (the server's lifecycle: not once dispatched). */
internal val CANCELLABLE_STATUSES = setOf("pending", "confirmed", "preparing")

/**
 * The order's status timeline (COM-703): the lifecycle from `pending` to `delivered`, each step with
 * when it was reached ([Order.statusHistory]; `pending` is when the order was placed). Steps
 * before the current status are done and later ones are upcoming. A cancelled order shows the
 * steps it went through and then the cancellation.
 */
fun Order.timeline(): List<TimelineStep> {
    val reached = buildMap {
        createdAt?.let { put("pending", it) }
        statusHistory.forEach { change ->
            val status = change.toStatus ?: return@forEach
            change.occurredAt?.let { put(status, it) }
        }
    }
    if (status == "cancelled") {
        val path = listOf("pending") + statusHistory.mapNotNull { it.toStatus }.filter { it != "pending" }
        val steps = (if (path.last() == "cancelled") path else path + "cancelled").distinct()
        return steps.mapIndexed { index, step ->
            val state = if (index == steps.lastIndex) TimelineStepState.CURRENT else TimelineStepState.DONE
            TimelineStep(step, reached[step], state)
        }
    }
    val current = ORDER_PATH.indexOf(status)
    return ORDER_PATH.mapIndexed { index, step ->
        val state = when {
            current < 0 -> TimelineStepState.UPCOMING
            index < current -> TimelineStepState.DONE
            index == current -> TimelineStepState.CURRENT
            else -> TimelineStepState.UPCOMING
        }
        TimelineStep(step, reached[step].takeIf { state != TimelineStepState.UPCOMING }, state)
    }
}

/** Whether [Order] can still be cancelled: it has not been dispatched yet. */
val Order.canCancel: Boolean get() = status in CANCELLABLE_STATUSES

/** Observable state of the order detail (COM-703). */
data class OrderDetailUiState(
    val isLoading: Boolean = true,
    val order: Order? = null,
    /** The order shown is the device's copy: the server could not be reached, for this reason. */
    val refreshError: OrderError? = null,
    /** Why the order could not be loaded at all. */
    val loadError: OrderError? = null,
    /** The user asked to cancel, waiting for confirmation. */
    val confirmingCancel: Boolean = false,
    val isCancelling: Boolean = false,
    /** Why the last cancellation failed. */
    val cancelError: OrderError? = null,
    /** The server rejected the session: the screen sends the user to sign in again. */
    val sessionExpired: Boolean = false,
) {
    val timeline: List<TimelineStep> get() = order?.timeline().orEmpty()

    /** Cancel is offered: the order is not dispatched yet and no cancellation is under way. */
    val canCancel: Boolean get() = order?.canCancel == true && !isCancelling

    /** What is left to pay the order with (an OXXO voucher, a SPEI transfer, a PayPal approval). */
    val paymentInstructions: PaymentInstructions get() = order?.paymentInstructions() ?: PaymentInstructions.None
}

/**
 * Shared logic of the order detail (COM-703), used by the Compose and SwiftUI screens: one order's
 * items, totals, delivery and status timeline, cache-first then refreshed
 * ([CommerceUseCases.order]), with a cancel action while the order can still be cancelled.
 *
 * Cancelling asks for confirmation first. An order the server says can no longer be cancelled
 * ([OrderError.CONFLICT], for example dispatched meanwhile) is read again so the screen shows where
 * it is now.
 */
class OrderDetailViewModel(private val useCases: CommerceUseCases) {

    private val _state = MutableStateFlow(OrderDetailUiState())
    val state: StateFlow<OrderDetailUiState> = _state.asStateFlow()

    /** Load order [orderId]: the device's copy first, then the server's. */
    suspend fun load(orderId: String) {
        _state.update { it.copy(isLoading = true) }
        useCases.order(orderId).collect { result ->
            when (result) {
                is OrderResult.Success -> _state.update {
                    it.copy(
                        order = result.value.value,
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

    /** Ask to cancel the order; nothing happens until [confirmCancel]. */
    fun requestCancel() {
        if (_state.value.canCancel) _state.update { it.copy(confirmingCancel = true, cancelError = null) }
    }

    fun dismissCancel() {
        _state.update { it.copy(confirmingCancel = false) }
    }

    /** Cancel the order. Returns true when it was cancelled. */
    suspend fun confirmCancel(): Boolean {
        val order = _state.value.order ?: return false
        if (_state.value.isCancelling) return false
        _state.update { it.copy(confirmingCancel = false, isCancelling = true, cancelError = null) }
        return when (val result = useCases.cancelOrder(order.id)) {
            is OrderResult.Success -> {
                _state.update { it.copy(isCancelling = false, order = result.value) }
                true
            }
            is OrderResult.Failure -> {
                _state.update {
                    it.copy(
                        isCancelling = false,
                        cancelError = result.error,
                        sessionExpired = it.sessionExpired || result.error == OrderError.SESSION_EXPIRED,
                    )
                }
                // The order moved on (dispatched, or cancelled elsewhere): show where it is now.
                if (result.error == OrderError.CONFLICT) load(order.id)
                false
            }
        }
    }

    fun dismissCancelError() {
        _state.update { it.copy(cancelError = null) }
    }

    /** The current UI state, for callers that read rather than observe it (e.g. the SwiftUI bridge). */
    fun currentState(): OrderDetailUiState = _state.value
}
