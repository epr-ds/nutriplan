@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.nutriplan.android.screen.checkout

import androidx.annotation.StringRes
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
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.CreditCard
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
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
import com.nutriplan.android.component.EmptyState
import com.nutriplan.android.component.ErrorState
import com.nutriplan.android.di.koinInject
import com.nutriplan.android.i18n.paymentMethodsMessageRes
import com.nutriplan.shared.commerce.AddPaymentMethodError
import com.nutriplan.shared.commerce.PaymentMethodsUiState
import com.nutriplan.shared.commerce.PaymentMethodsViewModel
import com.nutriplan.shared.data.model.PaymentMethod
import kotlinx.coroutines.launch

/** Test tags for the payment-method screen (used by the Robolectric UI tests). */
object PaymentMethodsTestTags {
    const val LIST = "payment_methods_list"
    const val LOADING = "payment_methods_loading"
    const val EMPTY = "payment_methods_empty"
    const val LOAD_ERROR = "payment_methods_load_error"
    const val ERROR_BANNER = "payment_methods_error_banner"
    const val METHOD_CARD = "payment_methods_card"
    const val DELETE = "payment_methods_delete"
    const val ADD = "payment_methods_add"
    const val SECURE_NOTE = "payment_methods_secure_note"
    const val CONFIRM_DELETE = "payment_methods_confirm_delete"
}

/**
 * COM-603: the user's saved payment methods -- list, add and delete, with loading, empty and error
 * states. A method is added through the payment provider's own secure form (COM-508), which gives
 * back a token; the app never sees a card number. Until that form is available on this device the
 * screen lists and deletes only. [onSessionExpired] is called when the server rejects the session.
 */
@Composable
fun PaymentMethodsScreen(onBack: () -> Unit, onSessionExpired: () -> Unit) {
    val viewModel = koinInject<PaymentMethodsViewModel>()
    val state by viewModel.state.collectAsState()
    val scope = rememberCoroutineScope()

    LaunchedEffect(viewModel) { viewModel.load() }
    LaunchedEffect(state.sessionExpired) { if (state.sessionExpired) onSessionExpired() }

    PaymentMethodsScreenContent(
        state = state,
        onBack = onBack,
        onRetry = { scope.launch { viewModel.load() } },
        onAdd = { scope.launch { viewModel.add() } },
        onRequestDelete = viewModel::requestDelete,
        onConfirmDelete = { scope.launch { viewModel.confirmDelete() } },
        onCancelDelete = viewModel::cancelDelete,
        onDismissError = viewModel::dismissError,
    )
}

/** Stateless payment-method screen: renders [state]; every action is a callback. */
@Composable
fun PaymentMethodsScreenContent(
    state: PaymentMethodsUiState,
    onBack: () -> Unit,
    onRetry: () -> Unit,
    onAdd: () -> Unit,
    onRequestDelete: (PaymentMethod) -> Unit,
    onConfirmDelete: () -> Unit,
    onCancelDelete: () -> Unit,
    onDismissError: () -> Unit,
) {
    val loadingDescription = stringResource(R.string.cd_payment_methods_loading)
    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = stringResource(R.string.payment_methods_title),
                        modifier = Modifier.semantics { heading() },
                    )
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
                state.isLoading && state.methods.isEmpty() -> Box(
                    modifier = Modifier.fillMaxSize().testTag(PaymentMethodsTestTags.LOADING),
                    contentAlignment = Alignment.Center,
                ) {
                    CircularProgressIndicator(modifier = Modifier.semantics { contentDescription = loadingDescription })
                }
                loadError != null && state.methods.isEmpty() -> ErrorState(
                    message = stringResource(loadError.paymentMethodsMessageRes()),
                    onRetry = onRetry,
                    actionLabel = stringResource(R.string.payment_methods_retry),
                    modifier = Modifier.testTag(PaymentMethodsTestTags.LOAD_ERROR),
                )
                state.isEmpty && !state.canAdd -> EmptyState(
                    title = stringResource(R.string.payment_methods_empty_title),
                    description = stringResource(R.string.payment_methods_empty_description),
                    modifier = Modifier.testTag(PaymentMethodsTestTags.EMPTY),
                )
                else -> MethodList(state, onAdd, onRequestDelete, onDismissError)
            }
        }
    }

    state.confirmingDelete?.let { method ->
        val name = method.displayName()
        AlertDialog(
            onDismissRequest = onCancelDelete,
            title = { Text(stringResource(R.string.payment_methods_delete_title)) },
            text = { Text(stringResource(R.string.payment_methods_delete_message, name)) },
            confirmButton = {
                TextButton(
                    onClick = onConfirmDelete,
                    enabled = !state.isDeleting,
                    modifier = Modifier.testTag(PaymentMethodsTestTags.CONFIRM_DELETE),
                ) { Text(stringResource(R.string.payment_methods_delete)) }
            },
            dismissButton = {
                TextButton(onClick = onCancelDelete) { Text(stringResource(R.string.payment_methods_keep)) }
            },
        )
    }
}

@Composable
private fun MethodList(
    state: PaymentMethodsUiState,
    onAdd: () -> Unit,
    onRequestDelete: (PaymentMethod) -> Unit,
    onDismissError: () -> Unit,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize().testTag(PaymentMethodsTestTags.LIST),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        val message = state.addError?.messageRes() ?: state.actionError?.paymentMethodsMessageRes()
        if (message != null) {
            item(key = "error") { ErrorBanner(message, onDismissError) }
        }
        if (state.isEmpty) {
            item(key = "empty") {
                EmptyState(
                    title = stringResource(R.string.payment_methods_empty_title),
                    description = stringResource(R.string.payment_methods_empty_add_description),
                    modifier = Modifier.testTag(PaymentMethodsTestTags.EMPTY),
                )
            }
        }
        items(state.methods, key = { it.id }) { method ->
            MethodCard(method, onDelete = { onRequestDelete(method) })
        }
        if (state.canAdd) {
            item(key = "add") {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    val addDescription = stringResource(R.string.payment_methods_add)
                    Button(
                        onClick = onAdd,
                        enabled = !state.isAdding,
                        modifier = Modifier
                            .fillMaxWidth()
                            .testTag(PaymentMethodsTestTags.ADD)
                            .semantics(mergeDescendants = true) { contentDescription = addDescription },
                    ) {
                        if (state.isAdding) {
                            CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
                        } else {
                            Icon(Icons.Default.Add, contentDescription = addDescription)
                        }
                        Text(stringResource(R.string.payment_methods_add), modifier = Modifier.padding(start = 8.dp))
                    }
                    SecureNote()
                }
            }
        }
    }
}

@Composable
private fun MethodCard(method: PaymentMethod, onDelete: () -> Unit) {
    val name = method.displayName()
    val deleteDescription = stringResource(R.string.cd_payment_methods_delete, name)
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .testTag(PaymentMethodsTestTags.METHOD_CARD)
            .semantics(mergeDescendants = true) {},
    ) {
        Row(
            modifier = Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            // Decorative: the name says what it is.
            Icon(Icons.Default.CreditCard, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(text = name, style = MaterialTheme.typography.titleMedium)
                val expiry = method.expMonth?.let { month ->
                    method.expYear?.let { year -> stringResource(R.string.payment_methods_expires, month.toString().padStart(2, '0'), year.toString()) }
                }
                Text(
                    text = listOfNotNull(stringResource(method.typeLabelRes()), expiry).joinToString(" · "),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            TextButton(
                onClick = onDelete,
                modifier = Modifier
                    .testTag(PaymentMethodsTestTags.DELETE)
                    .semantics { contentDescription = deleteDescription },
            ) { Text(stringResource(R.string.payment_methods_delete)) }
        }
    }
}

@Composable
private fun SecureNote() {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        modifier = Modifier.testTag(PaymentMethodsTestTags.SECURE_NOTE),
    ) {
        Icon(Icons.Default.Lock, contentDescription = null, modifier = Modifier.size(16.dp))
        Text(
            text = stringResource(R.string.payment_methods_secure_note),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun ErrorBanner(@StringRes message: Int, onDismiss: () -> Unit) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .fillMaxWidth()
            .testTag(PaymentMethodsTestTags.ERROR_BANNER)
            .semantics { liveRegion = LiveRegionMode.Polite },
    ) {
        Text(
            text = stringResource(message),
            color = MaterialTheme.colorScheme.error,
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.weight(1f),
        )
        TextButton(onClick = onDismiss) { Text(stringResource(R.string.payment_methods_dismiss)) }
    }
}

/** How a method is called on screen: "Visa •••• 4242" for a card, its type for a wallet. */
@Composable
private fun PaymentMethod.displayName(): String {
    val last4 = last4
    val brandName = brand?.takeIf(String::isNotBlank)?.replaceFirstChar(Char::uppercase)
    return when {
        last4 != null -> stringResource(R.string.payment_methods_card_name, brandName ?: stringResource(typeLabelRes()), last4)
        brandName != null -> brandName
        else -> stringResource(typeLabelRes())
    }
}

@StringRes
private fun PaymentMethod.typeLabelRes(): Int = when (type) {
    "credit_card" -> R.string.payment_type_credit_card
    "debit_card" -> R.string.payment_type_debit_card
    "paypal" -> R.string.payment_type_paypal
    "oxxo" -> R.string.payment_type_oxxo
    "spei" -> R.string.payment_type_spei
    else -> R.string.payment_type_other
}

@StringRes
private fun AddPaymentMethodError.messageRes(): Int = when (this) {
    AddPaymentMethodError.TOKENIZATION_FAILED -> R.string.error_payment_methods_tokenization
}
