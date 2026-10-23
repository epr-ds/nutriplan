package com.nutriplan.shared.commerce

import com.nutriplan.shared.data.local.AddressBookStore
import com.nutriplan.shared.data.local.SavedAddress
import com.nutriplan.shared.data.model.OrderAddress
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** COM-601: the address book's list, add/edit form, contract checks and error states. */
class AddressBookViewModelTest {

    /** An in-memory [AddressBookStore]; [failing] makes every call throw, like a broken database. */
    private class MemoryStore : AddressBookStore {
        val saved = mutableListOf<SavedAddress>()
        var failing = false
        private var nextId = 1L

        private fun check() {
            if (failing) error("database unavailable")
        }

        override fun getAll(): List<SavedAddress> {
            check()
            return saved.sortedByDescending { it.isDefault }
        }

        override fun save(address: OrderAddress, label: String?, makeDefault: Boolean): SavedAddress {
            check()
            if (makeDefault) clearDefault()
            return SavedAddress(nextId++, address, label, makeDefault).also { saved.add(0, it) }
        }

        override fun update(id: Long, address: OrderAddress, label: String?, makeDefault: Boolean): SavedAddress? {
            check()
            val index = saved.indexOfFirst { it.id == id }.takeIf { it >= 0 } ?: return null
            if (makeDefault) clearDefault()
            return saved[index].copy(address = address, label = label, isDefault = makeDefault || saved[index].isDefault)
                .also { saved[index] = it }
        }

        override fun setDefault(id: Long) {
            check()
            clearDefault()
            mapInPlace { if (it.id == id) it.copy(isDefault = true) else it }
        }

        override fun remove(id: Long) {
            check()
            saved.removeAll { it.id == id }
        }

        private fun clearDefault() = mapInPlace { it.copy(isDefault = false) }

        // Not MutableList.replaceAll: on Kotlin/Native (the iOS test build) that is an opt-in API.
        private fun mapInPlace(change: (SavedAddress) -> SavedAddress) {
            for (index in saved.indices) saved[index] = change(saved[index])
        }
    }

    private val store = MemoryStore()

    private fun newViewModel() = AddressBookViewModel(store, io = UnconfinedTestDispatcher())

    private val home = OrderAddress(
        street = "Av. Reforma 222",
        apartment = "4B",
        city = "Ciudad de México",
        state = "CDMX",
        zipCode = "06600",
        country = "MX",
        instructions = "Ring twice",
    )

    private fun AddressBookViewModel.fill(vararg values: Pair<AddressField, String>) =
        values.forEach { (field, value) -> onChange(field, value) }

    private fun AddressBookViewModel.fillValid() = fill(
        AddressField.STREET to "Insurgentes Sur 100",
        AddressField.ZIP_CODE to "03100",
        AddressField.CITY to "Ciudad de México",
        AddressField.STATE to "CDMX",
    )

    // --- list ---

    @Test
    fun `it starts loading and then shows the saved addresses`() = runTest {
        store.save(home, label = "Home", makeDefault = true)
        val viewModel = newViewModel()
        assertTrue(viewModel.state.value.isLoading)

        viewModel.load()

        val state = viewModel.state.value
        assertFalse(state.isLoading)
        assertEquals(listOf("Home"), state.addresses.map { it.label })
        assertFalse(state.isEmpty)
    }

    @Test
    fun `with nothing saved the book is empty`() = runTest {
        val viewModel = newViewModel()

        viewModel.load()

        assertTrue(viewModel.state.value.isEmpty)
    }

    @Test
    fun `a book that cannot be read is an error and not an empty book`() = runTest {
        store.failing = true
        val viewModel = newViewModel()

        viewModel.load()

        assertEquals(AddressBookError.READ_FAILED, viewModel.state.value.error)
        assertFalse(viewModel.state.value.isEmpty)
    }

    @Test
    fun `retrying after a read error shows the addresses`() = runTest {
        store.save(home)
        store.failing = true
        val viewModel = newViewModel()
        viewModel.load()

        store.failing = false
        viewModel.load()

        assertNull(viewModel.state.value.error)
        assertEquals(1, viewModel.state.value.addresses.size)
    }

    // --- adding ---

    @Test
    fun `a new address starts in Mexico and the first one becomes the default`() = runTest {
        val viewModel = newViewModel()
        viewModel.load()

        viewModel.startAdding()

        val form = viewModel.state.value.form!!
        assertNull(form.id)
        assertEquals("MX", form.value(AddressField.COUNTRY))
        assertTrue(form.makeDefault)
    }

    @Test
    fun `later addresses are not the default unless asked`() = runTest {
        store.save(home)
        val viewModel = newViewModel()
        viewModel.load()

        viewModel.startAdding()

        assertFalse(viewModel.state.value.form!!.makeDefault)
    }

    @Test
    fun `a valid new address is saved trimmed and the form closes`() = runTest {
        val viewModel = newViewModel()
        viewModel.load()
        viewModel.startAdding()
        viewModel.fill(
            AddressField.LABEL to " Office ",
            AddressField.STREET to " Insurgentes Sur 100 ",
            AddressField.APARTMENT to "  ",
            AddressField.ZIP_CODE to "03100",
            AddressField.CITY to "Ciudad de México",
            AddressField.STATE to "CDMX",
        )

        assertTrue(viewModel.save())

        val saved = store.saved.single()
        assertEquals("Office", saved.label)
        assertEquals("Insurgentes Sur 100", saved.address.street)
        assertNull(saved.address.apartment, "a blank optional field is left out")
        assertTrue(saved.isDefault)
        assertNull(viewModel.state.value.form)
        assertEquals(listOf(saved.id), viewModel.state.value.addresses.map { it.id })
    }

    // --- validation mirrors the contract ---

    @Test
    fun `every required field is checked`() = runTest {
        val viewModel = newViewModel()
        viewModel.startAdding()
        viewModel.onChange(AddressField.COUNTRY, " ")

        assertFalse(viewModel.save())

        val errors = viewModel.state.value.form!!.errors
        assertEquals(
            listOf(AddressField.STREET, AddressField.CITY, AddressField.STATE, AddressField.ZIP_CODE, AddressField.COUNTRY)
                .associateWith { AddressFieldError.REQUIRED },
            errors,
        )
        assertTrue(store.saved.isEmpty(), "nothing invalid is saved")
    }

    @Test
    fun `optional fields are never required`() = runTest {
        val viewModel = newViewModel()
        viewModel.startAdding()
        viewModel.fillValid()

        assertTrue(viewModel.validate())
    }

    @Test
    fun `a short zip code is invalid`() = runTest {
        val viewModel = newViewModel()
        viewModel.startAdding()
        viewModel.fillValid()
        viewModel.onChange(AddressField.ZIP_CODE, "0310")

        assertFalse(viewModel.validate())
        assertEquals(AddressFieldError.ZIP_CODE_INVALID, viewModel.state.value.form!!.error(AddressField.ZIP_CODE))
    }

    @Test
    fun `the zip code keeps digits only and at most five`() = runTest {
        val viewModel = newViewModel()
        viewModel.startAdding()

        viewModel.onChange(AddressField.ZIP_CODE, "03a1-00 99")

        assertEquals("03100", viewModel.state.value.form!!.value(AddressField.ZIP_CODE))
    }

    @Test
    fun `editing a field clears its error`() = runTest {
        val viewModel = newViewModel()
        viewModel.startAdding()
        viewModel.validate()

        viewModel.onChange(AddressField.STREET, "Madero 1")

        assertNull(viewModel.state.value.form!!.error(AddressField.STREET))
        assertEquals(AddressFieldError.REQUIRED, viewModel.state.value.form!!.error(AddressField.CITY))
    }

    // --- editing ---

    @Test
    fun `editing fills the form with the saved address`() = runTest {
        val saved = store.save(home, label = "Home", makeDefault = true)
        val viewModel = newViewModel()
        viewModel.load()

        viewModel.startEditing(saved.id)

        val form = viewModel.state.value.form!!
        assertEquals(saved.id, form.id)
        assertEquals("Home", form.value(AddressField.LABEL))
        assertEquals("4B", form.value(AddressField.APARTMENT))
        assertEquals("Ring twice", form.value(AddressField.INSTRUCTIONS))
        assertTrue(form.makeDefault)
    }

    @Test
    fun `an edit replaces the address in place`() = runTest {
        val saved = store.save(home, label = "Home")
        val viewModel = newViewModel()
        viewModel.load()
        viewModel.startEditing(saved.id)
        viewModel.onChange(AddressField.STREET, "Av. Reforma 300")
        viewModel.onChange(AddressField.LABEL, "")

        assertTrue(viewModel.save())

        val edited = store.saved.single()
        assertEquals(saved.id, edited.id)
        assertEquals("Av. Reforma 300", edited.address.street)
        assertNull(edited.label, "a cleared label is removed")
    }

    @Test
    fun `cancelling closes the form without saving`() = runTest {
        val viewModel = newViewModel()
        viewModel.startAdding()
        viewModel.fillValid()

        viewModel.cancelEditing()

        assertNull(viewModel.state.value.form)
        assertTrue(store.saved.isEmpty())
    }

    @Test
    fun `a save that fails keeps the form and what was typed`() = runTest {
        val viewModel = newViewModel()
        viewModel.startAdding()
        viewModel.fillValid()
        store.failing = true

        assertFalse(viewModel.save())

        val state = viewModel.state.value
        assertEquals(AddressBookError.SAVE_FAILED, state.error)
        assertEquals("Insurgentes Sur 100", state.form!!.value(AddressField.STREET))
        assertFalse(state.isSaving)
    }

    // --- list actions ---

    @Test
    fun `an address can be made the default`() = runTest {
        val first = store.save(home, makeDefault = true)
        val second = store.save(home.copy(street = "Madero 1"))
        val viewModel = newViewModel()
        viewModel.load()

        viewModel.setDefault(second.id)

        val addresses = viewModel.state.value.addresses
        assertEquals(second.id, addresses.first().id)
        assertFalse(addresses.first { it.id == first.id }.isDefault)
    }

    @Test
    fun `an address can be deleted`() = runTest {
        val saved = store.save(home)
        val viewModel = newViewModel()
        viewModel.load()

        viewModel.delete(saved.id)

        assertTrue(viewModel.state.value.isEmpty)
    }

    @Test
    fun `a delete that fails is reported`() = runTest {
        val saved = store.save(home)
        val viewModel = newViewModel()
        viewModel.load()
        store.failing = true

        viewModel.delete(saved.id)

        assertEquals(AddressBookError.SAVE_FAILED, viewModel.state.value.error)
    }
}
