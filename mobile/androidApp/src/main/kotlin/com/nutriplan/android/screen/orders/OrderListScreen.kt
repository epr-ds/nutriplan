@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.nutriplan.android.screen.orders

import androidx.annotation.StringRes
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.nutriplan.android.R
import com.nutriplan.android.component.EmptyState
import com.nutriplan.android.component.ErrorState
import com.nutriplan.android.di.koinInject
import com.nutriplan.android.i18n.ordersMessageRes
import com.nutriplan.android.screen.plans.formatPlanDay
import com.nutriplan.shared.commerce.OrderFilter
import com.nutriplan.shared.commerce.OrderListUiState
import com.nutriplan.shared.commerce.OrderListViewModel
import com.nutriplan.shared.data.model.Order
import kotlinx.coroutines.launch

/** Test tags for the order list (used by the Robolectric UI tests). */
object OrderListTestTags {
    const val LIST = "orders_list"
    const val LOADING = "orders_loading"
    const val EMPTY = "orders_empty"
    const val FILTERED_EMPTY = "orders_filtered_empty"
    const val LOAD_ERROR = "orders_load_error"
    const val STALE = "orders_stale"
    const val ORDER_CARD = "orders_card"
    const val STATUS = "orders_status"
    const val REORDER = "orders_reorder"

    /** The chip of [filter]. */
    fun filter(filter: OrderFilter): String = "orders_filter_${filter.name.lowercase()}"
}

/**
 * COM-701: the user's orders, newest first -- each with its status, delivery and total -- filtered
 * by status (all, active, delivered, cancelled), with loading, empty and error states. The orders
 * are shown from the device first and then refreshed; offline, the saved copy stays on screen with
 * a note. [onReorder] starts a new checkout with an order's delivery; [onOrderClick] opens it.
 */
@Composable
fun OrderListScreen(
    onOrderClick: (orderId: String) -> Unit,
    onReorder: (orderId: String) -> Unit,
    onBrowsePlans: () -> Unit,
    onBack: () -> Unit,
    onSessionExpired: () -> Unit,
) {
    val viewModel = koinInject<OrderListViewModel>()
    val state by viewModel.state.collectAsState()
    val scope = rememberCoroutineScope()

    LaunchedEffect(viewModel) { viewModel.load() }
    LaunchedEffect(state.sessionExpired) { if (state.sessionExpired) onSessionExpired() }

    OrderListScreenContent(
        state = state,
        canReorder = viewModel::canReorder,
        onBack = onBack,
        onRetry = { scope.launch { viewModel.load() } },
        onSelectFilter = viewModel::selectFilter,
        onOrderClick = onOrderClick,
        onReorder = onReorder,
        onBrowsePlans = onBrowsePlans,
    )
}

/** Stateless order list: renders [state]; every action is a callback. */
@Composable
fun OrderListScreenContent(
    state: OrderListUiState,
    canReorder: (Order) -> Boolean,
    onBack: () -> Unit,
    onRetry: () -> Unit,
    onSelectFilter: (OrderFilter) -> Unit,
    onOrderClick: (String) -> Unit,
    onReorder: (String) -> Unit,
    onBrowsePlans: () -> Unit,
) {
    val loadingDescription = stringResource(R.string.cd_orders_loading)
    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(text = stringResource(R.string.orders_title), modifier = Modifier.semantics { heading() })
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = stringResource(R.string.cd_meal_plans_back))
                    }
                },
            )
        },
    ) { padding ->
        val loadError = state.loadError
        Box(modifier = Modifier.fillMaxSize().padding(padding)) {
            when {
                state.isLoading && state.orders.isEmpty() -> Box(
                    modifier = Modifier.fillMaxSize().testTag(OrderListTestTags.LOADING),
                    contentAlignment = Alignment.Center,
                ) {
                    CircularProgressIndicator(modifier = Modifier.semantics { contentDescription = loadingDescription })
                }
                loadError != null && state.orders.isEmpty() -> ErrorState(
                    message = stringResource(loadError.ordersMessageRes()),
                    onRetry = onRetry,
                    actionLabel = stringResource(R.string.orders_retry),
                    modifier = Modifier.testTag(OrderListTestTags.LOAD_ERROR),
                )
                state.isEmpty -> EmptyState(
                    title = stringResource(R.string.orders_empty_title),
                    description = stringResource(R.string.orders_empty_description),
                    actionLabel = stringResource(R.string.orders_browse_plans),
                    onAction = onBrowsePlans,
                    modifier = Modifier.testTag(OrderListTestTags.EMPTY),
                )
                else -> OrderList(state, canReorder, onSelectFilter, onOrderClick, onReorder)
            }
        }
    }
}

@Composable
private fun OrderList(
    state: OrderListUiState,
    canReorder: (Order) -> Boolean,
    onSelectFilter: (OrderFilter) -> Unit,
    onOrderClick: (String) -> Unit,
    onReorder: (String) -> Unit,
) {
    Column(modifier = Modifier.fillMaxSize()) {
        Filters(state, onSelectFilter)
        LazyColumn(
            modifier = Modifier.fillMaxSize().testTag(OrderListTestTags.LIST),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            state.refreshError?.let {
                item(key = "stale") {
                    Text(
                        text = stringResource(R.string.orders_stale),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier
                            .testTag(OrderListTestTags.STALE)
                            .semantics { liveRegion = LiveRegionMode.Polite },
                    )
                }
            }
            if (state.isFilteredEmpty) {
                item(key = "filtered-empty") {
                    Text(
                        text = stringResource(R.string.orders_filtered_empty),
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.padding(vertical = 24.dp).testTag(OrderListTestTags.FILTERED_EMPTY),
                    )
                }
            }
            items(state.visibleOrders, key = { it.id }) { order ->
                OrderCard(
                    order = order,
                    canReorder = canReorder(order),
                    onClick = { onOrderClick(order.id) },
                    onReorder = { onReorder(order.id) },
                )
            }
        }
    }
}

@Composable
private fun Filters(state: OrderListUiState, onSelectFilter: (OrderFilter) -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .horizontalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        OrderFilter.entries.forEach { filter ->
            FilterChip(
                selected = state.filter == filter,
                onClick = { onSelectFilter(filter) },
                label = { Text(stringResource(R.string.orders_filter_count, stringResource(filter.labelRes()), state.count(filter))) },
                modifier = Modifier.testTag(OrderListTestTags.filter(filter)),
            )
        }
    }
}

@Composable
private fun OrderCard(order: Order, canReorder: Boolean, onClick: () -> Unit, onReorder: () -> Unit) {
    val placed = order.createdAt?.let { stringResource(R.string.orders_placed_on, formatPlanDay(it)) }
    val title = placed ?: stringResource(R.string.orders_order)
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .testTag(OrderListTestTags.ORDER_CARD)
            .clickable(role = Role.Button, onClick = onClick),
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(text = title, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                StatusChip(order.status)
            }
            val delivery = order.deliveryDate?.let { date ->
                stringResource(R.string.orders_delivery_on, formatPlanDay(date), order.deliveryTimeSlot.orEmpty())
            }
            Text(
                text = listOfNotNull(order.fulfillmentType?.let { stringResource(fulfillmentLabelRes(it)) }, delivery)
                    .joinToString(" · "),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            itemsSummary(order)?.let { Text(text = it, style = MaterialTheme.typography.bodyMedium) }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = order.total?.let { it.formatted ?: it.amount.toString() }.orEmpty(),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.weight(1f),
                )
                if (canReorder) {
                    val reorderDescription = stringResource(R.string.cd_orders_reorder, title)
                    TextButton(
                        onClick = onReorder,
                        modifier = Modifier
                            .testTag(OrderListTestTags.REORDER)
                            .semantics { contentDescription = reorderDescription },
                    ) { Text(stringResource(R.string.orders_reorder)) }
                }
            }
        }
    }
}

/** "Lentil soup and 2 more", or null for an order without items. */
@Composable
private fun itemsSummary(order: Order): String? {
    val names = order.items.mapNotNull { it.name?.takeIf(String::isNotBlank) }
    val first = names.firstOrNull() ?: return null
    return if (names.size == 1) first else stringResource(R.string.orders_items_more, first, names.size - 1)
}

@Composable
private fun StatusChip(status: String?) {
    val (container, content) = statusColors(status)
    Surface(
        color = container,
        contentColor = content,
        shape = MaterialTheme.shapes.small,
        modifier = Modifier.testTag(OrderListTestTags.STATUS),
    ) {
        Text(
            text = stringResource(statusLabelRes(status)),
            style = MaterialTheme.typography.labelMedium,
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
        )
    }
}

@Composable
private fun statusColors(status: String?): Pair<Color, Color> {
    val colors = MaterialTheme.colorScheme
    return when (status) {
        "pending" -> colors.tertiaryContainer to colors.onTertiaryContainer
        "confirmed", "preparing", "in_transit" -> colors.primaryContainer to colors.onPrimaryContainer
        "delivered" -> colors.secondaryContainer to colors.onSecondaryContainer
        "cancelled" -> colors.errorContainer to colors.onErrorContainer
        else -> colors.surfaceVariant to colors.onSurfaceVariant
    }
}

@StringRes
internal fun statusLabelRes(status: String?): Int = when (status) {
    "pending" -> R.string.order_status_pending
    "confirmed" -> R.string.order_status_confirmed
    "preparing" -> R.string.order_status_preparing
    "in_transit" -> R.string.order_status_in_transit
    "delivered" -> R.string.order_status_delivered
    "cancelled" -> R.string.order_status_cancelled
    else -> R.string.order_status_unknown
}

@StringRes
private fun fulfillmentLabelRes(type: String): Int = when (type) {
    "dark_kitchen" -> R.string.fulfillment_dark_kitchen
    "grocery_delivery" -> R.string.fulfillment_grocery_delivery
    else -> R.string.fulfillment_pickup
}

@StringRes
private fun OrderFilter.labelRes(): Int = when (this) {
    OrderFilter.ALL -> R.string.orders_filter_all
    OrderFilter.ACTIVE -> R.string.orders_filter_active
    OrderFilter.DELIVERED -> R.string.orders_filter_delivered
    OrderFilter.CANCELLED -> R.string.orders_filter_cancelled
}
