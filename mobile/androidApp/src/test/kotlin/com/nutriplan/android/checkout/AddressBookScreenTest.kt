package com.nutriplan.android.checkout

import android.content.Context
import androidx.annotation.StringRes
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasContentDescription
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextClearance
import androidx.compose.ui.test.performTextInput
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nutriplan.android.R
import com.nutriplan.android.a11y.TestApplication
import com.nutriplan.android.screen.checkout.AddressBookScreenContent
import com.nutriplan.android.screen.checkout.AddressBookTestTags
import com.nutriplan.android.ui.theme.NutriPlanTheme
import com.nutriplan.shared.commerce.AddressBookError
import com.nutriplan.shared.commerce.AddressBookUiState
import com.nutriplan.shared.commerce.AddressBookViewModel
import com.nutriplan.shared.commerce.AddressField
import com.nutriplan.shared.data.local.AddressBookStore
import com.nutriplan.shared.data.local.SavedAddress
import com.nutriplan.shared.data.model.OrderAddress
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

/**
 * COM-601: the address book lists, adds and edits delivery addresses with the contract's checks,
 * and shows loading, empty and error states. Runs on the JVM via Robolectric.
 */
@RunWith(AndroidJUnit4::class)
// A tall viewport so every lazily composed item is on screen.
@Config(sdk = [34], qualifiers = "en-rUS-w400dp-h2400dp", application = TestApplication::class)
class AddressBookScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val context: Context get() = ApplicationProvider.getApplicationContext()

    private fun str(@StringRes id: Int, vararg args: Any): String = context.getString(id, *args)

    /** An in-memory address store with the device store's ordering (default first). */
    private class MemoryStore : AddressBookStore {
        val saved = mutableListOf<SavedAddress>()
        private var nextId = 1L

        override fun getAll() = saved.sortedByDescending { it.isDefault }

        override fun save(address: OrderAddress, label: String?, makeDefault: Boolean): SavedAddress {
            if (makeDefault) saved.replaceAll { it.copy(isDefault = false) }
            return SavedAddress(nextId++, address, label, makeDefault).also { saved.add(0, it) }
        }

        override fun update(id: Long, address: OrderAddress, label: String?, makeDefault: Boolean): SavedAddress? {
            val index = saved.indexOfFirst { it.id == id }.takeIf { it >= 0 } ?: return null
            if (makeDefault) saved.replaceAll { it.copy(isDefault = false) }
            return saved[index].copy(address = address, label = label, isDefault = makeDefault || saved[index].isDefault)
                .also { saved[index] = it }
        }

        override fun setDefault(id: Long) {
            saved.replaceAll { it.copy(isDefault = it.id == id) }
        }

        override fun remove(id: Long) {
            saved.removeAll { it.id == id }
        }
    }

    private val store = MemoryStore()

    private val home = OrderAddress(
        street = "Av. Reforma 222",
        apartment = "4B",
        city = "Ciudad de México",
        state = "CDMX",
        zipCode = "06600",
        country = "MX",
    )

    /** Render the screen bound to a real view model, wired the way [AddressBookScreen] wires it. */
    private fun renderWithViewModel(): AddressBookViewModel {
        val viewModel = AddressBookViewModel(store, io = Dispatchers.Unconfined)
        runBlocking { viewModel.load() }
        compose.setContent {
            val state by viewModel.state.collectAsState()
            val scope = rememberCoroutineScope()
            NutriPlanTheme {
                AddressBookScreenContent(
                    state = state,
                    onBack = {},
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
        }
        return viewModel
    }

    private fun renderState(state: AddressBookUiState, onRetry: () -> Unit = {}) {
        compose.setContent {
            NutriPlanTheme {
                AddressBookScreenContent(
                    state = state,
                    onBack = {},
                    onRetry = onRetry,
                    onAdd = {},
                    onEdit = {},
                    onDelete = {},
                    onSetDefault = {},
                    onFieldChange = { _, _ -> },
                    onMakeDefaultChange = {},
                    onSave = {},
                    onCancel = {},
                )
            }
        }
    }

    private fun type(field: AddressField, text: String) {
        compose.onNodeWithTag(AddressBookTestTags.field(field)).performScrollTo().performTextInput(text)
    }

    private fun fillValidAddress() {
        type(AddressField.STREET, "Insurgentes Sur 100")
        type(AddressField.ZIP_CODE, "03100")
        type(AddressField.CITY, "Ciudad de México")
        type(AddressField.STATE, "CDMX")
    }

    // --- states ---

    @Test
    fun `while loading a labelled progress indicator is shown`() {
        renderState(AddressBookUiState(isLoading = true))

        compose.onNodeWithTag(AddressBookTestTags.LOADING).assertIsDisplayed()
        compose.onNodeWithContentDescription(str(R.string.cd_address_book_loading)).assertExists()
    }

    @Test
    fun `the title is a heading`() {
        renderWithViewModel()

        compose.onNode(isHeading() and hasText(str(R.string.address_book_title))).assertIsDisplayed()
    }

    @Test
    fun `the address book empty state is announced to screen readers`() {
        renderState(AddressBookUiState(isLoading = false))

        compose.onNode(
            hasTestTag(AddressBookTestTags.EMPTY) and hasContentDescription(
                str(R.string.address_book_empty_title),
            ),
        ).assertIsDisplayed()
    }

    @Test
    fun `with nothing saved the empty state offers to add an address`() {
        renderWithViewModel()

        compose.onNodeWithTag(AddressBookTestTags.EMPTY).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.address_book_empty_title)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.address_book_add)).performClick()

        compose.onNodeWithTag(AddressBookTestTags.FORM).assertIsDisplayed()
        compose.onNode(isHeading() and hasText(str(R.string.address_form_title_new))).assertIsDisplayed()
    }

    @Test
    fun `a book that cannot be read offers to retry`() {
        var retries = 0
        renderState(AddressBookUiState(isLoading = false, error = AddressBookError.READ_FAILED), onRetry = { retries++ })

        compose.onNodeWithText(str(R.string.address_book_error_read)).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.address_book_retry)).performClick()

        assertEquals(1, retries)
    }

    // --- list ---

    @Test
    fun `saved addresses are listed with the default one marked`() {
        store.save(home, label = "Home", makeDefault = true)
        store.save(home.copy(street = "Madero 1", zipCode = "06000"))
        renderWithViewModel()

        compose.onAllNodesWithTag(AddressBookTestTags.ADDRESS_CARD).assertCountEquals(2)
        compose.onNodeWithText("Home").assertIsDisplayed()
        compose.onNodeWithText("Av. Reforma 222 4B").assertIsDisplayed()
        compose.onNodeWithText(str(R.string.address_book_city_line, "06600", "Ciudad de México", "CDMX")).assertIsDisplayed()
        compose.onAllNodesWithTag(AddressBookTestTags.DEFAULT_BADGE).assertCountEquals(1)
        compose.onAllNodesWithTag(AddressBookTestTags.SET_DEFAULT).assertCountEquals(1)
    }

    @Test
    fun `an address can be made the default`() {
        store.save(home, label = "Home", makeDefault = true)
        val office = store.save(home.copy(street = "Madero 1"), label = "Office")
        renderWithViewModel()

        compose.onNodeWithContentDescription(str(R.string.cd_address_book_set_default, "Office")).performClick()
        compose.waitForIdle()

        assertTrue(store.saved.first { it.id == office.id }.isDefault)
    }

    @Test
    fun `an address can be deleted`() {
        store.save(home, label = "Home")
        renderWithViewModel()

        compose.onNodeWithContentDescription(str(R.string.cd_address_book_delete, "Home")).performClick()
        compose.waitForIdle()

        assertTrue(store.saved.isEmpty())
        compose.onNodeWithTag(AddressBookTestTags.EMPTY).assertIsDisplayed()
    }

    // --- add and edit ---

    @Test
    fun `a new address is added and listed`() {
        store.save(home, label = "Home", makeDefault = true)
        renderWithViewModel()

        compose.onNodeWithTag(AddressBookTestTags.ADD).performClick()
        type(AddressField.LABEL, "Office")
        fillValidAddress()
        compose.onNodeWithTag(AddressBookTestTags.SAVE).performScrollTo().performClick()
        compose.waitForIdle()

        assertEquals(2, store.saved.size)
        assertEquals("MX", store.saved.first { it.label == "Office" }.address.country)
        compose.onNodeWithText("Office").assertIsDisplayed()
    }

    @Test
    fun `the add address button is announced to screen readers`() {
        store.save(home, label = "Home", makeDefault = true)
        renderWithViewModel()

        compose.onNode(
            hasTestTag(AddressBookTestTags.ADD) and hasContentDescription(str(R.string.address_book_add)),
        ).assertIsDisplayed()
    }

    @Test
    fun `missing required fields are flagged and nothing is saved`() {
        renderWithViewModel()

        compose.onNodeWithText(str(R.string.address_book_add)).performClick()
        compose.onNodeWithTag(AddressBookTestTags.SAVE).performScrollTo().performClick()

        compose.onAllNodesWithText(str(R.string.address_form_error_required)).assertCountEquals(4)
        assertTrue(store.saved.isEmpty())
    }

    @Test
    fun `a short postal code is flagged`() {
        renderWithViewModel()

        compose.onNodeWithText(str(R.string.address_book_add)).performClick()
        fillValidAddress()
        compose.onNodeWithTag(AddressBookTestTags.field(AddressField.ZIP_CODE)).performTextClearance()
        type(AddressField.ZIP_CODE, "0310")
        compose.onNodeWithTag(AddressBookTestTags.SAVE).performScrollTo().performClick()

        compose.onNodeWithText(str(R.string.address_form_error_zip)).assertIsDisplayed()
        assertTrue(store.saved.isEmpty())
    }

    @Test
    fun `tapping an address opens it for editing and the edit is saved`() {
        store.save(home, label = "Home")
        renderWithViewModel()

        compose.onNodeWithContentDescription(str(R.string.cd_address_book_edit, "Home")).performClick()
        compose.onNode(isHeading() and hasText(str(R.string.address_form_title_edit))).assertIsDisplayed()
        compose.onNodeWithTag(AddressBookTestTags.field(AddressField.STREET)).performTextClearance()
        type(AddressField.STREET, "Av. Reforma 300")
        compose.onNodeWithTag(AddressBookTestTags.SAVE).performScrollTo().performClick()
        compose.waitForIdle()

        assertEquals("Av. Reforma 300", store.saved.single().address.street)
        compose.onNodeWithTag(AddressBookTestTags.LIST).assertIsDisplayed()
    }

    @Test
    fun `back from the form returns to the list without saving`() {
        store.save(home, label = "Home")
        renderWithViewModel()

        compose.onNodeWithTag(AddressBookTestTags.ADD).performClick()
        type(AddressField.STREET, "Madero 1")
        compose.onNodeWithContentDescription(str(R.string.cd_meal_plans_back)).performClick()

        compose.onNodeWithTag(AddressBookTestTags.LIST).assertIsDisplayed()
        assertEquals(1, store.saved.size)
    }

    @Test
    fun `a failed save is announced and keeps the form`() {
        renderState(
            AddressBookUiState(
                isLoading = false,
                form = com.nutriplan.shared.commerce.AddressForm(values = mapOf(AddressField.STREET to "Madero 1")),
                error = AddressBookError.SAVE_FAILED,
            ),
        )

        compose.onNodeWithTag(AddressBookTestTags.ERROR_BANNER).assertIsDisplayed()
        compose.onNodeWithText(str(R.string.address_book_error_save)).assertIsDisplayed()
        compose.onNodeWithTag(AddressBookTestTags.FORM).assertIsDisplayed()
    }
}
