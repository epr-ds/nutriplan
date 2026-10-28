@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.nutriplan.android.screen.orders

import androidx.annotation.StringRes
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
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
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.nutriplan.android.R
import com.nutriplan.android.component.ErrorState
import com.nutriplan.android.di.koinInject
import com.nutriplan.android.i18n.cancelOrderMessageRes
import com.nutriplan.android.i18n.orderDetailMessageRes
import com.nutriplan.android.screen.checkout.PaymentInstructionsCard
import com.nutriplan.android.screen.checkout.PriceRow
import com.nutriplan.android.screen.checkout.formatQuantity
import com.nutriplan.android.screen.plans.formatPlanDay
import com.nutriplan.shared.commerce.OrderDetailUiState
import com.nutriplan.shared.commerce.OrderDetailViewModel
import com.nutriplan.shared.commerce.PaymentInstructions
import com.nutriplan.shared.commerce.TimelineStep
import com.nutriplan.shared.commerce.TimelineStepState
import com.nutriplan.shared.data.model.Order
import com.nutriplan.shared.data.model.OrderAddress
import kotlinx.coroutines.launch
import java.text.DateFormat
import java.text.ParseException
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone

/** Test tags for the order detail (used by the Robolectric UI tests). */
object OrderDetailTestTags {
    const val CONTENT = "order_detail_content"
    const val LOADING = "order_detail_loading"
    const val LOAD_ERROR = "order_detail_load_error"
    const val STALE = "order_detail_stale"
    const val TIMELINE_STEP = "order_detail_timeline_step"
    const val ITEM = "order_detail_item"
    const val TOTAL = "order_detail_total"
    const val ADDRESS = "order_detail_address"
    const val CANCEL = "order_detail_cancel"
    const val CONFIRM_CANCEL = "order_detail_confirm_cancel"
    const val CANCEL_ERROR = "order_detail_cancel_error"
}

/**
 * COM-703: one order -- its status timeline, items and totals, and where and when it is delivered,
 * plus what is left to pay for an OXXO, SPEI or PayPal order still pending. The order can be
 * cancelled, after confirming, while it has not been dispatched. It is shown from the device first
 * and then refreshed; offline, the saved copy stays on screen with a note.
 */
@Composable
fun OrderDetailScreen(orderId: String, onBack: () -> Unit, onSessionExpired: () -> Unit) {
    val viewModel = koinInject<OrderDetailViewModel>()
    val state by viewModel.state.collectAsState()
    val scope = rememberCoroutineScope()

    LaunchedEffect(viewModel, orderId) { viewModel.load(orderId) }
    LaunchedEffect(state.sessionExpired) { if (state.sessionExpired) onSessionExpired() }

    OrderDetailScreenContent(
        state = state,
        onBack = onBack,
        onRetry = { scope.launch { viewModel.load(orderId) } },
        onRequestCancel = viewModel::requestCancel,
        onConfirmCancel = { scope.launch { viewModel.confirmCancel() } },
        onDismissCancel = viewModel::dismissCancel,
        onDismissCancelError = viewModel::dismissCancelError,
    )
}

/** Stateless order detail: renders [state]; every action is a callback. */
@Composable
fun OrderDetailScreenContent(
    state: OrderDetailUiState,
    onBack: () -> Unit,
    onRetry: () -> Unit,
    onRequestCancel: () -> Unit,
    onConfirmCancel: () -> Unit,
    onDismissCancel: () -> Unit,
    onDismissCancelError: () -> Unit,
) {
    val loadingDescription = stringResource(R.string.cd_order_detail_loading)
    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(text = stringResource(R.string.order_detail_title), modifier = Modifier.semantics { heading() })
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = stringResource(R.string.cd_meal_plans_back))
                    }
                },
            )
        },
    ) { padding ->
        val order = state.order
        val loadError = state.loadError
        Box(modifier = Modifier.fillMaxSize().padding(padding)) {
            when {
                order == null && loadError != null -> ErrorState(
                    message = stringResource(loadError.orderDetailMessageRes()),
                    onRetry = onRetry,
                    actionLabel = stringResource(R.string.orders_retry),
                    modifier = Modifier.testTag(OrderDetailTestTags.LOAD_ERROR),
                )
                order == null -> Box(
                    modifier = Modifier.fillMaxSize().testTag(OrderDetailTestTags.LOADING),
                    contentAlignment = Alignment.Center,
                ) {
                    CircularProgressIndicator(modifier = Modifier.semantics { contentDescription = loadingDescription })
                }
                else -> OrderDetail(state, order, onRequestCancel, onDismissCancelError)
            }
        }
    }

    if (state.confirmingCancel) {
        AlertDialog(
            onDismissRequest = onDismissCancel,
            title = { Text(stringResource(R.string.order_detail_cancel_title)) },
            text = { Text(stringResource(R.string.order_detail_cancel_message)) },
            confirmButton = {
                TextButton(
                    onClick = onConfirmCancel,
                    modifier = Modifier.testTag(OrderDetailTestTags.CONFIRM_CANCEL),
                ) { Text(stringResource(R.string.order_detail_cancel)) }
            },
            dismissButton = {
                TextButton(onClick = onDismissCancel) { Text(stringResource(R.string.order_detail_keep)) }
            },
        )
    }
}

@Composable
private fun OrderDetail(
    state: OrderDetailUiState,
    order: Order,
    onRequestCancel: () -> Unit,
    onDismissCancelError: () -> Unit,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize().testTag(OrderDetailTestTags.CONTENT),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item(key = "header") {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                val placed = order.createdAt?.let { stringResource(R.string.orders_placed_on, formatPlanDay(it)) }
                Text(
                    text = placed ?: stringResource(R.string.orders_order),
                    style = MaterialTheme.typography.titleLarge,
                    modifier = Modifier.weight(1f),
                )
                StatusChip(order.status)
            }
        }
        state.refreshError?.let {
            item(key = "stale") {
                Text(
                    text = stringResource(R.string.order_detail_stale),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier
                        .testTag(OrderDetailTestTags.STALE)
                        .semantics { liveRegion = LiveRegionMode.Polite },
                )
            }
        }
        state.cancelError?.let { error ->
            item(key = "cancel-error") {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag(OrderDetailTestTags.CANCEL_ERROR)
                        .semantics { liveRegion = LiveRegionMode.Polite },
                ) {
                    Text(
                        text = stringResource(error.cancelOrderMessageRes()),
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.weight(1f),
                    )
                    TextButton(onClick = onDismissCancelError) { Text(stringResource(R.string.payment_methods_dismiss)) }
                }
            }
        }
        val instructions = state.paymentInstructions
        if (instructions != PaymentInstructions.None) {
            item(key = "instructions") { PaymentInstructionsCard(instructions, order.total) }
        }

        item(key = "status-heading") { SectionHeading(R.string.order_detail_status_heading) }
        items(state.timeline, key = { "step-${it.status}" }) { step -> TimelineRow(step) }

        item(key = "items-heading") { SectionHeading(R.string.order_detail_items_heading) }
        items(order.items.withIndex().toList(), key = { "item-${it.index}" }) { (_, line) ->
            PriceRow(
                label = stringResource(R.string.checkout_line, line.name.orEmpty(), formatQuantity(line.quantity)),
                amount = line.lineTotal,
                modifier = Modifier.testTag(OrderDetailTestTags.ITEM),
            )
        }
        item(key = "totals") {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                HorizontalDivider()
                PriceRow(stringResource(R.string.checkout_subtotal), order.subtotal)
                PriceRow(stringResource(R.string.checkout_delivery_fee), order.deliveryFee)
                PriceRow(
                    label = stringResource(R.string.checkout_total),
                    amount = order.total,
                    bold = true,
                    modifier = Modifier.testTag(OrderDetailTestTags.TOTAL),
                )
            }
        }

        item(key = "delivery-heading") { SectionHeading(R.string.order_detail_delivery_heading) }
        item(key = "delivery") { Delivery(order) }

        if (state.canCancel) {
            item(key = "cancel") {
                OutlinedButton(
                    onClick = onRequestCancel,
                    modifier = Modifier.fillMaxWidth().testTag(OrderDetailTestTags.CANCEL),
                ) { Text(stringResource(R.string.order_detail_cancel)) }
            }
        }
        if (state.isCancelling) {
            item(key = "cancelling") {
                val loadingDescription = stringResource(R.string.cd_order_detail_loading)
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .semantics { contentDescription = loadingDescription },
                    contentAlignment = Alignment.Center,
                ) {
                    CircularProgressIndicator(modifier = Modifier.size(24.dp), strokeWidth = 2.dp)
                }
            }
        }
    }
}

@Composable
private fun SectionHeading(@StringRes text: Int) {
    Text(
        text = stringResource(text),
        style = MaterialTheme.typography.titleMedium,
        modifier = Modifier.padding(top = 8.dp).semantics { heading() },
    )
}

@Composable
private fun TimelineRow(step: TimelineStep) {
    val colors = MaterialTheme.colorScheme
    val (dot, text) = when (step.state) {
        TimelineStepState.DONE -> colors.primary to colors.onSurface
        TimelineStepState.CURRENT -> colors.primary to colors.primary
        TimelineStepState.UPCOMING -> colors.outlineVariant to colors.onSurfaceVariant
    }
    val label = stringResource(statusLabelRes(step.status))
    val stateLabel = stringResource(
        when (step.state) {
            TimelineStepState.DONE -> R.string.order_timeline_done
            TimelineStepState.CURRENT -> R.string.order_timeline_current
            TimelineStepState.UPCOMING -> R.string.order_timeline_upcoming
        },
    )
    val reachedAt = step.reachedAt?.let(::formatOrderTime)
    val description = listOfNotNull(stringResource(R.string.order_timeline_step, label, stateLabel), reachedAt).joinToString(", ")
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        modifier = Modifier
            .fillMaxWidth()
            .testTag(OrderDetailTestTags.TIMELINE_STEP)
            .semantics(mergeDescendants = true) { contentDescription = description },
    ) {
        Box(modifier = Modifier.size(12.dp).background(dot, CircleShape))
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = label,
                color = text,
                style = if (step.state == TimelineStepState.CURRENT) MaterialTheme.typography.titleSmall else MaterialTheme.typography.bodyMedium,
            )
            reachedAt?.let {
                Text(text = it, style = MaterialTheme.typography.bodySmall, color = colors.onSurfaceVariant)
            }
        }
    }
}

@Composable
private fun Delivery(order: Order) {
    Column(
        verticalArrangement = Arrangement.spacedBy(4.dp),
        modifier = Modifier.testTag(OrderDetailTestTags.ADDRESS),
    ) {
        val kind = order.fulfillmentType?.let { stringResource(fulfillmentLabelRes(it)) }
        val store = order.provider?.let { it.name ?: it.id }?.let { stringResource(R.string.order_detail_store, it) }
        listOfNotNull(kind, store).takeIf { it.isNotEmpty() }?.let {
            Text(text = it.joinToString(" · "), style = MaterialTheme.typography.bodyMedium)
        }
        order.deliveryDate?.let { date ->
            Text(
                text = listOfNotNull(formatPlanDay(date), order.deliveryTimeSlot).joinToString(", "),
                style = MaterialTheme.typography.bodyMedium,
            )
        }
        order.deliveryAddress?.let { address ->
            addressLines(address).forEach { Text(text = it, style = MaterialTheme.typography.bodyMedium) }
            address.instructions?.takeIf(String::isNotBlank)?.let {
                Text(
                    text = stringResource(R.string.order_detail_instructions, it),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

/** "Reforma 222, 4B" / "CDMX, CDMX 06600" / "MX". */
internal fun addressLines(address: OrderAddress): List<String> = listOf(
    listOfNotNull(address.street, address.apartment?.takeIf(String::isNotBlank)).joinToString(", "),
    "${address.city}, ${address.state} ${address.zipCode}",
    address.country,
)

/** An ISO date-time (UTC) as a medium date and short time in the device's zone; the input when it cannot be read. */
internal fun formatOrderTime(isoDateTime: String, locale: Locale = Locale.getDefault()): String {
    val parser = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US).apply {
        isLenient = false
        timeZone = TimeZone.getTimeZone("UTC")
    }
    val date = try {
        parser.parse(isoDateTime.take(ISO_DATE_TIME_LENGTH))
    } catch (e: ParseException) {
        null
    } ?: return isoDateTime
    return DateFormat.getDateTimeInstance(DateFormat.MEDIUM, DateFormat.SHORT, locale).format(date)
}

private const val ISO_DATE_TIME_LENGTH = 19
