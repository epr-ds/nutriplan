@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.nutriplan.android.screen.checkout

import androidx.activity.compose.BackHandler
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
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
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
import androidx.compose.ui.semantics.toggleableState
import androidx.compose.ui.state.ToggleableState
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.nutriplan.android.R
import com.nutriplan.android.component.EmptyState
import com.nutriplan.android.component.ErrorState
import com.nutriplan.android.di.koinInject
import com.nutriplan.shared.commerce.AddressBookError
import com.nutriplan.shared.commerce.AddressBookUiState
import com.nutriplan.shared.commerce.AddressBookViewModel
import com.nutriplan.shared.commerce.AddressField
import com.nutriplan.shared.commerce.AddressFieldError
import com.nutriplan.shared.commerce.AddressForm
import com.nutriplan.shared.data.local.SavedAddress
import kotlinx.coroutines.launch

/** Test tags for the address book screen (used by the Robolectric UI tests). */
object AddressBookTestTags {
    const val LIST = "address_book_list"
    const val LOADING = "address_book_loading"
    const val EMPTY = "address_book_empty"
    const val READ_ERROR = "address_book_read_error"
    const val ERROR_BANNER = "address_book_error_banner"
    const val ADD = "address_book_add"
    const val ADDRESS_CARD = "address_book_card"
    const val DEFAULT_BADGE = "address_book_default_badge"
    const val SET_DEFAULT = "address_book_set_default"
    const val DELETE = "address_book_delete"
    const val FORM = "address_book_form"
    const val MAKE_DEFAULT = "address_book_make_default"
    const val SAVE = "address_book_save"
    const val CANCEL = "address_book_cancel"

    /** The tag of the form's text field for [field]. */
    fun field(field: AddressField): String = "address_book_field_${field.name.lowercase()}"
}

/**
 * COM-601: the user's delivery addresses -- list, add and edit, with the contract's checks (street,
 * city, state, a five-digit zip code and country are required) and loading, empty and error states.
 * The addresses live on the device ([AddressBookViewModel] over the COM-503 address store), so the
 * screen works offline too.
 */
@Composable
fun AddressBookScreen(onBack: () -> Unit) {
    val viewModel = koinInject<AddressBookViewModel>()
    val state by viewModel.state.collectAsState()
    val scope = rememberCoroutineScope()

    LaunchedEffect(viewModel) { viewModel.load() }

    AddressBookScreenContent(
        state = state,
        onBack = onBack,
        onRetry = { scope.launch { viewModel.load() } },
        onAdd = viewModel::startAdding,
        onEdit = viewModel::startEditing,
        onDelete = { id -> scope.launch { viewModel.delete(id) } },
        onSetDefault = { id -> scope.launch { viewModel.setDefault(id) } },
        onFieldChange = viewModel::onChange,
        onMakeDefaultChange = viewModel::onMakeDefaultChange,
        onSave = { scope.launch { viewModel.save() } },
        onCancel = viewModel::cancelEditing,
    )
}

/** Stateless address book: renders [state]; every action is a callback. */
@Composable
fun AddressBookScreenContent(
    state: AddressBookUiState,
    onBack: () -> Unit,
    onRetry: () -> Unit,
    onAdd: () -> Unit,
    onEdit: (Long) -> Unit,
    onDelete: (Long) -> Unit,
    onSetDefault: (Long) -> Unit,
    onFieldChange: (AddressField, String) -> Unit,
    onMakeDefaultChange: (Boolean) -> Unit,
    onSave: () -> Unit,
    onCancel: () -> Unit,
) {
    val form = state.form
    // With the form open, Back closes it instead of leaving the screen.
    BackHandler(enabled = form != null, onBack = onCancel)

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = stringResource(
                            when {
                                form == null -> R.string.address_book_title
                                form.id == null -> R.string.address_form_title_new
                                else -> R.string.address_form_title_edit
                            },
                        ),
                        modifier = Modifier.semantics { heading() },
                    )
                },
                navigationIcon = {
                    IconButton(onClick = if (form != null) onCancel else onBack) {
                        Icon(
                            Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = stringResource(R.string.cd_meal_plans_back),
                        )
                    }
                },
            )
        },
    ) { padding ->
        Box(modifier = Modifier.fillMaxSize().padding(padding)) {
            if (form != null) {
                AddressFormContent(
                    form = form,
                    isSaving = state.isSaving,
                    saveFailed = state.error == AddressBookError.SAVE_FAILED,
                    onFieldChange = onFieldChange,
                    onMakeDefaultChange = onMakeDefaultChange,
                    onSave = onSave,
                    onCancel = onCancel,
                )
            } else {
                AddressList(state, onRetry, onAdd, onEdit, onDelete, onSetDefault)
            }
        }
    }
}

@Composable
private fun AddressList(
    state: AddressBookUiState,
    onRetry: () -> Unit,
    onAdd: () -> Unit,
    onEdit: (Long) -> Unit,
    onDelete: (Long) -> Unit,
    onSetDefault: (Long) -> Unit,
) {
    val loadingDescription = stringResource(R.string.cd_address_book_loading)
    when {
        state.isLoading && state.addresses.isEmpty() -> Box(
            modifier = Modifier.fillMaxSize().testTag(AddressBookTestTags.LOADING),
            contentAlignment = Alignment.Center,
        ) {
            CircularProgressIndicator(modifier = Modifier.semantics { contentDescription = loadingDescription })
        }
        state.error == AddressBookError.READ_FAILED -> ErrorState(
            message = stringResource(R.string.address_book_error_read),
            onRetry = onRetry,
            actionLabel = stringResource(R.string.address_book_retry),
            modifier = Modifier.testTag(AddressBookTestTags.READ_ERROR),
        )
        state.isEmpty -> EmptyState(
            title = stringResource(R.string.address_book_empty_title),
            description = stringResource(R.string.address_book_empty_description),
            actionLabel = stringResource(R.string.address_book_add),
            onAction = onAdd,
            modifier = Modifier.testTag(AddressBookTestTags.EMPTY),
        )
        else -> LazyColumn(
            modifier = Modifier.fillMaxSize().testTag(AddressBookTestTags.LIST),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (state.error == AddressBookError.SAVE_FAILED) {
                item(key = "error") { SaveErrorBanner() }
            }
            items(state.addresses, key = { it.id }) { saved ->
                AddressCard(
                    saved = saved,
                    onEdit = { onEdit(saved.id) },
                    onDelete = { onDelete(saved.id) },
                    onSetDefault = { onSetDefault(saved.id) },
                )
            }
            item(key = "add") {
                Button(
                    onClick = onAdd,
                    modifier = Modifier.fillMaxWidth().testTag(AddressBookTestTags.ADD),
                ) {
                    Icon(Icons.Default.Add, contentDescription = null)
                    Text(stringResource(R.string.address_book_add), modifier = Modifier.padding(start = 8.dp))
                }
            }
        }
    }
}

/** The name an address goes by: its label, or else its street. */
private fun SavedAddress.title(): String = label?.takeIf(String::isNotBlank) ?: address.street

@Composable
private fun AddressCard(saved: SavedAddress, onEdit: () -> Unit, onDelete: () -> Unit, onSetDefault: () -> Unit) {
    val title = saved.title()
    val editDescription = stringResource(R.string.cd_address_book_edit, title)
    val address = saved.address
    Card(
        onClick = onEdit,
        modifier = Modifier
            .fillMaxWidth()
            .testTag(AddressBookTestTags.ADDRESS_CARD)
            .semantics { contentDescription = editDescription },
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(text = title, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                if (saved.isDefault) {
                    AssistChip(
                        onClick = {},
                        label = { Text(stringResource(R.string.address_book_default_badge)) },
                        modifier = Modifier.testTag(AddressBookTestTags.DEFAULT_BADGE),
                    )
                }
            }
            Text(
                text = listOfNotNull(address.street, address.apartment).joinToString(" "),
                style = MaterialTheme.typography.bodyMedium,
            )
            Text(
                text = stringResource(R.string.address_book_city_line, address.zipCode, address.city, address.state),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (!saved.isDefault) {
                    val setDefaultDescription = stringResource(R.string.cd_address_book_set_default, title)
                    TextButton(
                        onClick = onSetDefault,
                        modifier = Modifier
                            .testTag(AddressBookTestTags.SET_DEFAULT)
                            .semantics { contentDescription = setDefaultDescription },
                    ) { Text(stringResource(R.string.address_book_set_default)) }
                }
                val deleteDescription = stringResource(R.string.cd_address_book_delete, title)
                TextButton(
                    onClick = onDelete,
                    modifier = Modifier
                        .testTag(AddressBookTestTags.DELETE)
                        .semantics { contentDescription = deleteDescription },
                ) { Text(stringResource(R.string.address_book_delete)) }
            }
        }
    }
}

@Composable
private fun SaveErrorBanner() {
    Text(
        text = stringResource(R.string.address_book_error_save),
        color = MaterialTheme.colorScheme.error,
        style = MaterialTheme.typography.bodyMedium,
        modifier = Modifier
            .testTag(AddressBookTestTags.ERROR_BANNER)
            .semantics { liveRegion = LiveRegionMode.Polite },
    )
}

@Composable
private fun AddressFormContent(
    form: AddressForm,
    isSaving: Boolean,
    saveFailed: Boolean,
    onFieldChange: (AddressField, String) -> Unit,
    onMakeDefaultChange: (Boolean) -> Unit,
    onSave: () -> Unit,
    onCancel: () -> Unit,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize().testTag(AddressBookTestTags.FORM),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        if (saveFailed) item(key = "error") { SaveErrorBanner() }
        items(FORM_FIELDS, key = { it.name }) { field ->
            AddressTextField(form, field, onFieldChange)
        }
        item(key = "default") {
            val makeDefaultLabel = stringResource(R.string.address_form_make_default)
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .fillMaxWidth()
                    .testTag(AddressBookTestTags.MAKE_DEFAULT)
                    .semantics(mergeDescendants = true) {
                        contentDescription = makeDefaultLabel
                        toggleableState = ToggleableState(form.makeDefault)
                    },
            ) {
                Text(text = makeDefaultLabel, modifier = Modifier.weight(1f))
                Switch(checked = form.makeDefault, onCheckedChange = onMakeDefaultChange)
            }
        }
        item(key = "actions") {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = onSave,
                    enabled = !isSaving,
                    modifier = Modifier.fillMaxWidth().testTag(AddressBookTestTags.SAVE),
                ) { Text(stringResource(R.string.address_form_save)) }
                OutlinedButton(
                    onClick = onCancel,
                    modifier = Modifier.fillMaxWidth().testTag(AddressBookTestTags.CANCEL),
                ) { Text(stringResource(R.string.address_form_cancel)) }
            }
        }
    }
}

@Composable
private fun AddressTextField(form: AddressForm, field: AddressField, onFieldChange: (AddressField, String) -> Unit) {
    val error = form.error(field)
    OutlinedTextField(
        value = form.value(field),
        onValueChange = { onFieldChange(field, it) },
        label = { Text(stringResource(field.labelRes())) },
        singleLine = field != AddressField.INSTRUCTIONS,
        isError = error != null,
        supportingText = when (error) {
            AddressFieldError.REQUIRED -> ({ Text(stringResource(R.string.address_form_error_required)) })
            AddressFieldError.ZIP_CODE_INVALID -> ({ Text(stringResource(R.string.address_form_error_zip)) })
            null -> if (field == AddressField.LABEL) ({ Text(stringResource(R.string.address_form_label_hint)) }) else null
        },
        keyboardOptions = KeyboardOptions(
            keyboardType = if (field == AddressField.ZIP_CODE) KeyboardType.Number else KeyboardType.Text,
            capitalization = if (field == AddressField.ZIP_CODE) KeyboardCapitalization.None else KeyboardCapitalization.Words,
            imeAction = if (field == AddressField.INSTRUCTIONS) ImeAction.Done else ImeAction.Next,
        ),
        modifier = Modifier.fillMaxWidth().testTag(AddressBookTestTags.field(field)),
    )
}

/** The form's fields in reading order. */
private val FORM_FIELDS = listOf(
    AddressField.LABEL,
    AddressField.STREET,
    AddressField.APARTMENT,
    AddressField.ZIP_CODE,
    AddressField.CITY,
    AddressField.STATE,
    AddressField.COUNTRY,
    AddressField.INSTRUCTIONS,
)

private fun AddressField.labelRes(): Int = when (this) {
    AddressField.LABEL -> R.string.address_form_label
    AddressField.STREET -> R.string.address_form_street
    AddressField.APARTMENT -> R.string.address_form_apartment
    AddressField.CITY -> R.string.address_form_city
    AddressField.STATE -> R.string.address_form_state
    AddressField.ZIP_CODE -> R.string.address_form_zip
    AddressField.COUNTRY -> R.string.address_form_country
    AddressField.INSTRUCTIONS -> R.string.address_form_instructions
}
