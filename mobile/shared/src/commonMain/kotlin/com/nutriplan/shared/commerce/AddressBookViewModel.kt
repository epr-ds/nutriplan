package com.nutriplan.shared.commerce

import com.nutriplan.shared.data.local.AddressBookStore
import com.nutriplan.shared.data.local.SavedAddress
import com.nutriplan.shared.data.model.OrderAddress
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.IO
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.withContext
import kotlin.coroutines.cancellation.CancellationException

/** A field of the address form, in the contract's `AddressRequest` terms, plus the user's [LABEL]. */
enum class AddressField {
    LABEL,
    STREET,
    APARTMENT,
    CITY,
    STATE,
    ZIP_CODE,
    COUNTRY,
    INSTRUCTIONS,
}

/** A problem with one field of the address form, shown inline. Locale-neutral (IDN-902 convention). */
enum class AddressFieldError {
    /** The contract requires this field. */
    REQUIRED,

    /** A postal code must be five digits. */
    ZIP_CODE_INVALID,
}

/** Why the address book could not be read or changed, shown for the whole screen. */
enum class AddressBookError {
    READ_FAILED,
    SAVE_FAILED,
}

/**
 * The address being added or edited: [id] null for a new one. [values] hold the raw text of each
 * field so nothing typed is ever lost.
 */
data class AddressForm(
    val id: Long? = null,
    val values: Map<AddressField, String> = emptyMap(),
    val makeDefault: Boolean = false,
    val errors: Map<AddressField, AddressFieldError> = emptyMap(),
) {
    fun value(field: AddressField): String = values[field].orEmpty()

    fun error(field: AddressField): AddressFieldError? = errors[field]
}

/** Observable state of the address book screen (COM-601). */
data class AddressBookUiState(
    val isLoading: Boolean = true,
    val addresses: List<SavedAddress> = emptyList(),
    val error: AddressBookError? = null,
    /** The add/edit form when it is open; the list otherwise. */
    val form: AddressForm? = null,
    val isSaving: Boolean = false,
) {
    /** Loaded, readable, and nothing saved yet. */
    val isEmpty: Boolean get() = !isLoading && error != AddressBookError.READ_FAILED && addresses.isEmpty()
}

/**
 * Shared logic of the address book (COM-601) used by the Compose and SwiftUI screens: the list of
 * delivery addresses kept on the device ([AddressBookStore], COM-503), and a form to add or edit one.
 *
 * - The form's checks mirror the contract's `AddressRequest`: street, city, state, zip code and
 *   country are required, and the zip code is five digits. Apartment, delivery instructions and the
 *   label ("Home") are optional; blank ones are left out.
 * - A new address defaults to Mexico, and the very first one becomes the default.
 * - The store is on the device, so reads and writes run on [io]; [CancellationException] is rethrown
 *   so leaving the screen cancels cleanly.
 */
class AddressBookViewModel(
    private val store: AddressBookStore,
    private val io: CoroutineDispatcher = Dispatchers.IO,
) {

    private val _state = MutableStateFlow(AddressBookUiState())
    val state: StateFlow<AddressBookUiState> = _state.asStateFlow()

    /** Read the saved addresses. */
    suspend fun load() {
        _state.update { it.copy(isLoading = true) }
        val addresses = readAll()
        _state.update {
            if (addresses == null) {
                it.copy(isLoading = false, error = AddressBookError.READ_FAILED)
            } else {
                it.copy(isLoading = false, addresses = addresses, error = null)
            }
        }
    }

    /** Open the form for a new address. */
    fun startAdding() {
        _state.update {
            it.copy(
                form = AddressForm(values = mapOf(AddressField.COUNTRY to DEFAULT_COUNTRY), makeDefault = it.addresses.isEmpty()),
                error = null,
            )
        }
    }

    /** Open the form on the saved address [id]. */
    fun startEditing(id: Long) {
        val saved = _state.value.addresses.firstOrNull { it.id == id } ?: return
        val address = saved.address
        _state.update {
            it.copy(
                form = AddressForm(
                    id = saved.id,
                    values = mapOf(
                        AddressField.LABEL to saved.label.orEmpty(),
                        AddressField.STREET to address.street,
                        AddressField.APARTMENT to address.apartment.orEmpty(),
                        AddressField.CITY to address.city,
                        AddressField.STATE to address.state,
                        AddressField.ZIP_CODE to address.zipCode,
                        AddressField.COUNTRY to address.country,
                        AddressField.INSTRUCTIONS to address.instructions.orEmpty(),
                    ),
                    makeDefault = saved.isDefault,
                ),
                error = null,
            )
        }
    }

    /** Change one field. The zip code keeps digits only, at most five. */
    fun onChange(field: AddressField, value: String) {
        val kept = if (field == AddressField.ZIP_CODE) value.filter(Char::isDigit).take(ZIP_LENGTH) else value
        updateForm { it.copy(values = it.values + (field to kept), errors = it.errors - field) }
    }

    fun onMakeDefaultChange(makeDefault: Boolean) {
        updateForm { it.copy(makeDefault = makeDefault) }
    }

    /** Close the form without saving. */
    fun cancelEditing() {
        _state.update { it.copy(form = null, isSaving = false, error = null) }
    }

    /** Checks every field, setting the inline errors. Returns true when the form can be saved. */
    fun validate(): Boolean {
        val form = _state.value.form ?: return false
        val errors = buildMap {
            REQUIRED.forEach { field -> if (form.value(field).isBlank()) put(field, AddressFieldError.REQUIRED) }
            val zip = form.value(AddressField.ZIP_CODE).trim()
            if (zip.isNotEmpty() && !zip.isMexicanZipCode()) put(AddressField.ZIP_CODE, AddressFieldError.ZIP_CODE_INVALID)
        }
        updateForm { it.copy(errors = errors) }
        return errors.isEmpty()
    }

    /** Save the open form (a new address or an edit). Returns true when it was saved and the form closed. */
    suspend fun save(): Boolean {
        val form = _state.value.form ?: return false
        if (!validate()) return false
        _state.update { it.copy(isSaving = true, error = null) }
        val address = form.toAddress()
        val label = form.value(AddressField.LABEL).cleaned()
        val saved = write {
            if (form.id == null) {
                store.save(address, label = label, makeDefault = form.makeDefault)
            } else {
                store.update(form.id, address, label = label, makeDefault = form.makeDefault)
            }
        }
        if (!saved) {
            _state.update { it.copy(isSaving = false, error = AddressBookError.SAVE_FAILED) }
            return false
        }
        _state.update { it.copy(form = null, isSaving = false) }
        load()
        return true
    }

    /** Forget the address [id]. */
    suspend fun delete(id: Long) {
        if (write { store.remove(id) }) load() else _state.update { it.copy(error = AddressBookError.SAVE_FAILED) }
    }

    /** Make the address [id] the default one. */
    suspend fun setDefault(id: Long) {
        if (write { store.setDefault(id) }) load() else _state.update { it.copy(error = AddressBookError.SAVE_FAILED) }
    }

    private fun updateForm(change: (AddressForm) -> AddressForm) {
        _state.update { state -> state.form?.let { state.copy(form = change(it), error = null) } ?: state }
    }

    private suspend fun readAll(): List<SavedAddress>? = try {
        withContext(io) { store.getAll() }
    } catch (e: CancellationException) {
        throw e
    } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
        null
    }

    /** Run a write on [io]; false when the store failed. */
    private suspend fun write(block: () -> Unit): Boolean = try {
        withContext(io) { block() }
        true
    } catch (e: CancellationException) {
        throw e
    } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
        false
    }

    private fun AddressForm.toAddress() = OrderAddress(
        street = value(AddressField.STREET).trim(),
        apartment = value(AddressField.APARTMENT).cleaned(),
        city = value(AddressField.CITY).trim(),
        state = value(AddressField.STATE).trim(),
        zipCode = value(AddressField.ZIP_CODE).trim(),
        country = value(AddressField.COUNTRY).trim(),
        instructions = value(AddressField.INSTRUCTIONS).cleaned(),
    )

    private fun String.cleaned(): String? = trim().takeIf(String::isNotEmpty)

    private companion object {
        const val DEFAULT_COUNTRY = "MX"
        const val ZIP_LENGTH = 5
        val REQUIRED = listOf(AddressField.STREET, AddressField.CITY, AddressField.STATE, AddressField.ZIP_CODE, AddressField.COUNTRY)
    }
}
