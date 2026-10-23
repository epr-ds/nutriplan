@file:OptIn(
    androidx.compose.material3.ExperimentalMaterial3Api::class,
    androidx.compose.foundation.layout.ExperimentalLayoutApi::class,
)

package com.nutriplan.android.screen.checkout

import androidx.activity.compose.BackHandler
import androidx.annotation.StringRes
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.selection.selectable
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.RadioButton
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
import com.nutriplan.android.di.koinInjectRetained
import com.nutriplan.android.i18n.checkoutMessageRes
import com.nutriplan.android.screen.plans.formatPlanDay
import com.nutriplan.android.screen.plans.todayIso
import com.nutriplan.shared.commerce.CheckoutStep
import com.nutriplan.shared.commerce.CheckoutStepError
import com.nutriplan.shared.commerce.CheckoutUiState
import com.nutriplan.shared.commerce.CheckoutViewModel
import com.nutriplan.shared.data.model.Money
import com.nutriplan.shared.planning.IsoDate
import kotlinx.coroutines.launch

/** Test tags for the checkout stepper (used by the Robolectric UI tests). */
object CheckoutTestTags {
    const val STEP_TITLE = "checkout_step_title"
    const val NEXT = "checkout_next"
    const val BACK = "checkout_back"
    const val PLACE_ORDER = "checkout_place_order"
    const val STEP_ERROR = "checkout_step_error"
    const val ERROR_BANNER = "checkout_error_banner"
    const val RETRY = "checkout_retry"
    const val LOADING = "checkout_loading"
    const val OPTION = "checkout_option"
    const val SLOT = "checkout_slot"
    const val DAY = "checkout_day"
    const val MANAGE_ADDRESSES = "checkout_manage_addresses"
    const val QUOTE_LINE = "checkout_quote_line"
    const val QUOTE_TOTAL = "checkout_quote_total"
    const val EMPTY = "checkout_empty"

    /** The "Edit" link of [step] on the review step. */
    fun edit(step: CheckoutStep): String = "checkout_edit_${step.name.lowercase()}"
}

/** How many days ahead a delivery can be scheduled. */
private const val SCHEDULE_DAYS = 14

/**
 * COM-605: check out a meal plan in steps -- plan, how it is fulfilled, delivery address, day and
 * time slot, and a review with the itemized price -- each validated before moving on, and any step
 * editable from the review. [planId] preselects the plan (from the plan's detail). Choosing how to
 * pay comes with COM-608; until then the order is placed unpaid (`pending`).
 */
@Composable
fun CheckoutScreen(
    planId: String?,
    onOrderPlaced: (orderId: String) -> Unit,
    onManageAddresses: () -> Unit,
    onBack: () -> Unit,
    onSessionExpired: () -> Unit,
) {
    // Kept while the user manages addresses, so coming back keeps every choice made so far.
    val viewModel = koinInjectRetained<CheckoutViewModel>()
    val state by viewModel.state.collectAsState()
    val scope = rememberCoroutineScope()

    LaunchedEffect(viewModel) {
        val current = viewModel.state.value
        if (current.plansLoading && current.plans.isEmpty()) viewModel.start(todayIso(), planId) else viewModel.refreshAddresses()
    }
    LaunchedEffect(state.sessionExpired) { if (state.sessionExpired) onSessionExpired() }
    LaunchedEffect(state.placedOrderId) { state.placedOrderId?.let(onOrderPlaced) }

    CheckoutScreenContent(
        state = state,
        today = todayIso(),
        onBack = { if (!viewModel.back()) onBack() },
        onNext = { scope.launch { viewModel.next() } },
        onSelectPlan = viewModel::selectPlan,
        onSelectFulfillment = { type -> scope.launch { viewModel.selectFulfillment(type) } },
        onSelectProvider = viewModel::selectProvider,
        onSelectAddress = viewModel::selectAddress,
        onManageAddresses = onManageAddresses,
        onSelectDay = { day -> scope.launch { viewModel.onDateChange(day) } },
        onSelectSlot = viewModel::selectSlot,
        onEdit = { step -> scope.launch { viewModel.edit(step) } },
        onRetry = {
            scope.launch {
                when (state.step) {
                    CheckoutStep.SLOT -> viewModel.loadSlots()
                    CheckoutStep.REVIEW -> viewModel.loadQuote()
                    else -> viewModel.start(todayIso(), planId)
                }
            }
        },
        onPlaceOrder = { scope.launch { viewModel.placeOrder() } },
    )
}

/** Stateless checkout stepper: renders [state]; every action is a callback. */
@Composable
fun CheckoutScreenContent(
    state: CheckoutUiState,
    today: String,
    onBack: () -> Unit,
    onNext: () -> Unit,
    onSelectPlan: (String) -> Unit,
    onSelectFulfillment: (String) -> Unit,
    onSelectProvider: (String) -> Unit,
    onSelectAddress: (Long) -> Unit,
    onManageAddresses: () -> Unit,
    onSelectDay: (String) -> Unit,
    onSelectSlot: (String) -> Unit,
    onEdit: (CheckoutStep) -> Unit,
    onRetry: () -> Unit,
    onPlaceOrder: () -> Unit,
) {
    BackHandler(onBack = onBack)
    val stepNumber = state.step.ordinal + 1
    val stepCount = CheckoutStep.entries.size

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(text = stringResource(R.string.checkout_title), modifier = Modifier.semantics { heading() })
                        Text(
                            text = stringResource(R.string.checkout_step_of, stepNumber, stepCount, stringResource(state.step.titleRes())),
                            style = MaterialTheme.typography.bodySmall,
                            modifier = Modifier.testTag(CheckoutTestTags.STEP_TITLE),
                        )
                    }
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = stringResource(R.string.cd_meal_plans_back))
                    }
                },
            )
        },
        bottomBar = { StepActions(state, onBack, onNext, onPlaceOrder) },
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item(key = "heading") {
                Text(
                    text = stringResource(state.step.titleRes()),
                    style = MaterialTheme.typography.titleLarge,
                    modifier = Modifier.semantics { heading() },
                )
            }
            state.error?.let { error ->
                item(key = "error") { ErrorBanner(error.checkoutMessageRes(), onRetry) }
            }
            state.stepError?.let { problem ->
                item(key = "step-error") {
                    Text(
                        text = stringResource(problem.messageRes()),
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier
                            .testTag(CheckoutTestTags.STEP_ERROR)
                            .semantics { liveRegion = LiveRegionMode.Polite },
                    )
                }
            }
            when (state.step) {
                CheckoutStep.PLAN -> planStep(state, onSelectPlan)
                CheckoutStep.FULFILLMENT -> fulfillmentStep(state, onSelectFulfillment, onSelectProvider)
                CheckoutStep.ADDRESS -> addressStep(state, onSelectAddress, onManageAddresses)
                CheckoutStep.SLOT -> slotStep(state, today, onSelectDay, onSelectSlot)
                CheckoutStep.REVIEW -> reviewStep(state, onEdit)
            }
        }
    }
}

// --- steps ---------------------------------------------------------------------------------------

private fun LazyListScope.planStep(state: CheckoutUiState, onSelectPlan: (String) -> Unit) {
    when {
        state.plansLoading -> item(key = "loading") { Loading() }
        state.plans.isEmpty() -> item(key = "empty") {
            EmptyState(
                title = stringResource(R.string.checkout_no_plans_title),
                description = stringResource(R.string.checkout_no_plans_description),
                modifier = Modifier.testTag(CheckoutTestTags.EMPTY),
            )
        }
        else -> items(state.plans, key = { it.id }) { plan ->
            Option(
                title = plan.name,
                subtitle = stringResource(R.string.checkout_plan_dates, formatPlanDay(plan.startDate), formatPlanDay(plan.endDate)),
                selected = plan.id == state.planId,
                onClick = { onSelectPlan(plan.id) },
            )
        }
    }
}

private val FULFILLMENT_OPTIONS = listOf("dark_kitchen", "grocery_delivery", "pickup")

private fun LazyListScope.fulfillmentStep(
    state: CheckoutUiState,
    onSelectFulfillment: (String) -> Unit,
    onSelectProvider: (String) -> Unit,
) {
    items(FULFILLMENT_OPTIONS, key = { it }) { type ->
        Option(
            title = stringResource(fulfillmentLabelRes(type)),
            subtitle = stringResource(fulfillmentDescriptionRes(type)),
            selected = type == state.fulfillmentType,
            onClick = { onSelectFulfillment(type) },
        )
    }
    if (state.fulfillmentType == "grocery_delivery") {
        item(key = "providers-heading") {
            Text(
                text = stringResource(R.string.checkout_provider_heading),
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.semantics { heading() },
            )
        }
        if (state.providersLoading) {
            item(key = "providers-loading") { Loading() }
        } else {
            items(state.providers, key = { "provider-${it.id}" }) { provider ->
                Option(
                    title = provider.name ?: provider.id.orEmpty(),
                    subtitle = provider.estimatedDelivery,
                    selected = provider.id == state.providerId,
                    onClick = { provider.id?.let(onSelectProvider) },
                )
            }
        }
    }
}

private fun LazyListScope.addressStep(
    state: CheckoutUiState,
    onSelectAddress: (Long) -> Unit,
    onManageAddresses: () -> Unit,
) {
    if (state.addresses.isEmpty()) {
        item(key = "empty") {
            EmptyState(
                title = stringResource(R.string.checkout_no_addresses_title),
                description = stringResource(R.string.checkout_no_addresses_description),
                actionLabel = stringResource(R.string.address_book_add),
                onAction = onManageAddresses,
                modifier = Modifier.testTag(CheckoutTestTags.EMPTY),
            )
        }
        return
    }
    items(state.addresses, key = { "address-${it.id}" }) { saved ->
        val address = saved.address
        Option(
            title = saved.label?.takeIf(String::isNotBlank) ?: address.street,
            subtitle = stringResource(R.string.address_book_city_line, address.zipCode, address.city, address.state),
            selected = saved.id == state.addressId,
            onClick = { onSelectAddress(saved.id) },
        )
    }
    item(key = "manage") {
        TextButton(onClick = onManageAddresses, modifier = Modifier.testTag(CheckoutTestTags.MANAGE_ADDRESSES)) {
            Text(stringResource(R.string.checkout_manage_addresses))
        }
    }
}

private fun LazyListScope.slotStep(
    state: CheckoutUiState,
    today: String,
    onSelectDay: (String) -> Unit,
    onSelectSlot: (String) -> Unit,
) {
    item(key = "days") {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(stringResource(R.string.checkout_day_heading), style = MaterialTheme.typography.titleMedium)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                (0 until SCHEDULE_DAYS).mapNotNull { IsoDate.addDays(today, it) }.forEach { day ->
                    FilterChip(
                        selected = day == state.deliveryDate,
                        onClick = { onSelectDay(day) },
                        label = { Text(formatPlanDay(day)) },
                        modifier = Modifier.testTag(CheckoutTestTags.DAY),
                    )
                }
            }
        }
    }
    item(key = "slots") {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(stringResource(R.string.checkout_slot_heading), style = MaterialTheme.typography.titleMedium)
            if (state.slotsLoading) {
                Loading()
            } else {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    state.slots.forEach { slot ->
                        FilterChip(
                            selected = slot == state.timeSlot,
                            onClick = { onSelectSlot(slot) },
                            label = { Text(slot) },
                            modifier = Modifier.testTag(CheckoutTestTags.SLOT),
                        )
                    }
                }
            }
        }
    }
}

private fun LazyListScope.reviewStep(state: CheckoutUiState, onEdit: (CheckoutStep) -> Unit) {
    item(key = "summary") {
        Card(modifier = Modifier.fillMaxWidth()) {
            Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                SummaryRow(CheckoutStep.PLAN, state.selectedPlan?.name.orEmpty(), onEdit)
                val fulfillment = state.fulfillmentType?.let { stringResource(fulfillmentLabelRes(it)) }.orEmpty()
                SummaryRow(
                    CheckoutStep.FULFILLMENT,
                    listOfNotNull(fulfillment, state.selectedProvider?.name).joinToString(" · "),
                    onEdit,
                )
                val address = state.selectedAddress?.address
                SummaryRow(
                    CheckoutStep.ADDRESS,
                    address?.let { "${it.street}, ${it.zipCode} ${it.city}" }.orEmpty(),
                    onEdit,
                )
                SummaryRow(
                    CheckoutStep.SLOT,
                    "${formatPlanDay(state.deliveryDate)} · ${state.timeSlot.orEmpty()}",
                    onEdit,
                )
            }
        }
    }
    item(key = "price-heading") {
        Text(
            text = stringResource(R.string.checkout_price_heading),
            style = MaterialTheme.typography.titleMedium,
            modifier = Modifier.semantics { heading() },
        )
    }
    val quote = state.quote
    when {
        state.quoteLoading -> item(key = "quote-loading") { Loading() }
        quote != null -> {
            items(quote.items.withIndex().toList(), key = { "line-${it.index}" }) { (_, line) ->
                PriceRow(
                    label = stringResource(R.string.checkout_line, line.name.orEmpty(), formatQuantity(line.quantity)),
                    amount = line.lineTotal,
                    modifier = Modifier.testTag(CheckoutTestTags.QUOTE_LINE),
                )
            }
            item(key = "totals") {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    HorizontalDivider()
                    PriceRow(stringResource(R.string.checkout_subtotal), quote.subtotal)
                    PriceRow(stringResource(R.string.checkout_delivery_fee), quote.deliveryFee)
                    PriceRow(
                        label = stringResource(R.string.checkout_total),
                        amount = quote.total,
                        bold = true,
                        modifier = Modifier.testTag(CheckoutTestTags.QUOTE_TOTAL),
                    )
                }
            }
            item(key = "pending-note") {
                Text(
                    text = stringResource(R.string.checkout_pending_note),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

// --- building blocks ---------------------------------------------------------------------------

@Composable
private fun StepActions(state: CheckoutUiState, onBack: () -> Unit, onNext: () -> Unit, onPlaceOrder: () -> Unit) {
    Surface(tonalElevation = 3.dp) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (state.step != CheckoutStep.PLAN) {
                OutlinedButton(onClick = onBack, modifier = Modifier.weight(1f).testTag(CheckoutTestTags.BACK)) {
                    Text(stringResource(R.string.checkout_back))
                }
            }
            if (state.step == CheckoutStep.REVIEW) {
                Button(
                    onClick = onPlaceOrder,
                    enabled = state.quote != null && !state.isPlacing,
                    modifier = Modifier.weight(1f).testTag(CheckoutTestTags.PLACE_ORDER),
                ) { Text(stringResource(R.string.checkout_place_order)) }
            } else {
                Button(onClick = onNext, modifier = Modifier.weight(1f).testTag(CheckoutTestTags.NEXT)) {
                    Text(stringResource(R.string.checkout_next))
                }
            }
        }
    }
}

@Composable
private fun Option(title: String, subtitle: String?, selected: Boolean, onClick: () -> Unit) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .testTag(CheckoutTestTags.OPTION)
            .selectable(selected = selected, onClick = onClick, role = Role.RadioButton),
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            // The whole card is the radio button; this one only shows its state.
            RadioButton(selected = selected, onClick = null)
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(text = title, style = MaterialTheme.typography.titleMedium)
                subtitle?.takeIf(String::isNotBlank)?.let {
                    Text(text = it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}

@Composable
private fun SummaryRow(step: CheckoutStep, value: String, onEdit: (CheckoutStep) -> Unit) {
    val stepTitle = stringResource(step.titleRes())
    val editDescription = stringResource(R.string.cd_checkout_edit, stepTitle)
    Row(verticalAlignment = Alignment.CenterVertically) {
        Column(modifier = Modifier.weight(1f)) {
            Text(text = stepTitle, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(text = value, style = MaterialTheme.typography.bodyMedium)
        }
        TextButton(
            onClick = { onEdit(step) },
            modifier = Modifier
                .testTag(CheckoutTestTags.edit(step))
                .semantics { contentDescription = editDescription },
        ) { Text(stringResource(R.string.checkout_edit)) }
    }
}

@Composable
private fun PriceRow(label: String, amount: Money?, modifier: Modifier = Modifier, bold: Boolean = false) {
    val weight = if (bold) FontWeight.Bold else FontWeight.Normal
    Row(modifier = modifier.fillMaxWidth().semantics(mergeDescendants = true) {}) {
        Text(text = label, fontWeight = weight, modifier = Modifier.weight(1f))
        // The server formats money (COM-501), currency included.
        Text(text = amount?.formatted ?: amount?.amount?.toString().orEmpty(), fontWeight = weight)
    }
}

@Composable
private fun Loading() {
    val description = stringResource(R.string.cd_checkout_loading)
    Box(
        modifier = Modifier.fillMaxWidth().padding(24.dp).testTag(CheckoutTestTags.LOADING),
        contentAlignment = Alignment.Center,
    ) {
        CircularProgressIndicator(modifier = Modifier.semantics { contentDescription = description })
    }
}

@Composable
private fun ErrorBanner(@StringRes message: Int, onRetry: () -> Unit) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .fillMaxWidth()
            .testTag(CheckoutTestTags.ERROR_BANNER)
            .semantics { liveRegion = LiveRegionMode.Polite },
    ) {
        Text(
            text = stringResource(message),
            color = MaterialTheme.colorScheme.error,
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.weight(1f),
        )
        TextButton(onClick = onRetry, modifier = Modifier.testTag(CheckoutTestTags.RETRY)) {
            Text(stringResource(R.string.checkout_retry))
        }
    }
}

// --- labels ------------------------------------------------------------------------------------

/** "2" for whole servings, "1.5" otherwise. */
private fun formatQuantity(quantity: Double?): String {
    val value = quantity ?: return "1"
    return if (value % 1.0 == 0.0) value.toLong().toString() else value.toString()
}

@StringRes
private fun CheckoutStep.titleRes(): Int = when (this) {
    CheckoutStep.PLAN -> R.string.checkout_step_plan
    CheckoutStep.FULFILLMENT -> R.string.checkout_step_fulfillment
    CheckoutStep.ADDRESS -> R.string.checkout_step_address
    CheckoutStep.SLOT -> R.string.checkout_step_slot
    CheckoutStep.REVIEW -> R.string.checkout_step_review
}

@StringRes
private fun fulfillmentLabelRes(type: String): Int = when (type) {
    "dark_kitchen" -> R.string.fulfillment_dark_kitchen
    "grocery_delivery" -> R.string.fulfillment_grocery_delivery
    else -> R.string.fulfillment_pickup
}

@StringRes
private fun fulfillmentDescriptionRes(type: String): Int = when (type) {
    "dark_kitchen" -> R.string.fulfillment_dark_kitchen_description
    "grocery_delivery" -> R.string.fulfillment_grocery_delivery_description
    else -> R.string.fulfillment_pickup_description
}

@StringRes
private fun CheckoutStepError.messageRes(): Int = when (this) {
    CheckoutStepError.PLAN_REQUIRED -> R.string.checkout_error_plan
    CheckoutStepError.FULFILLMENT_REQUIRED -> R.string.checkout_error_fulfillment
    CheckoutStepError.PROVIDER_REQUIRED -> R.string.checkout_error_provider
    CheckoutStepError.ADDRESS_REQUIRED -> R.string.checkout_error_address
    CheckoutStepError.DATE_INVALID -> R.string.checkout_error_date
    CheckoutStepError.SLOT_REQUIRED -> R.string.checkout_error_slot
    CheckoutStepError.AREA_NOT_SERVED -> R.string.checkout_error_area
}
