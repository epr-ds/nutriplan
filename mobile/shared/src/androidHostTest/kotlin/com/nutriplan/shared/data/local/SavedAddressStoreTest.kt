package com.nutriplan.shared.data.local

import com.nutriplan.shared.data.model.OrderAddress
import com.nutriplan.shared.testing.newDatabase
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** COM-503: delivery addresses are kept on the device, default first, then most recently used. */
class SavedAddressStoreTest {

    private val database = newDatabase()
    private val store = SavedAddressStore(database)

    private fun address(street: String, zipCode: String = "06600") = OrderAddress(
        street = street,
        city = "Ciudad de México",
        state = "CDMX",
        zipCode = zipCode,
        country = "MX",
    )

    @Test
    fun `an empty address book has no addresses`() {
        assertEquals(emptyList(), store.getAll())
        assertNull(store.preferred())
    }

    @Test
    fun `a saved address is read back with every field`() {
        val home = address("Av. Reforma 222").copy(apartment = "4B", instructions = "Ring twice")

        val saved = store.save(home, label = "Home")

        assertEquals(listOf(saved), store.getAll())
        assertEquals(home, saved.address)
        assertEquals("Home", saved.label)
        assertFalse(saved.isDefault)
    }

    @Test
    fun `the most recently used address comes first`() {
        store.save(address("Reforma 222"))
        store.save(address("Insurgentes 100"))

        assertEquals(listOf("Insurgentes 100", "Reforma 222"), store.getAll().map { it.address.street })
    }

    @Test
    fun `saving an address again moves it up instead of duplicating it`() {
        val first = store.save(address("Reforma 222"))
        store.save(address("Insurgentes 100"))

        val again = store.save(address("Reforma 222"))

        assertEquals(first.id, again.id)
        assertEquals(listOf("Reforma 222", "Insurgentes 100"), store.getAll().map { it.address.street })
    }

    @Test
    fun `saving again keeps the label unless a new one is given`() {
        store.save(address("Reforma 222"), label = "Home")

        assertEquals("Home", store.save(address("Reforma 222")).label)
        assertEquals("Office", store.save(address("Reforma 222"), label = "Office").label)
        assertEquals(1, store.getAll().size)
    }

    @Test
    fun `the default address comes first however old it is, and only one is default`() {
        val home = store.save(address("Reforma 222"), makeDefault = true)
        store.save(address("Insurgentes 100"))
        store.save(address("Madero 1"))

        assertEquals(home.id, store.preferred()?.id)
        assertTrue(store.getAll().first().isDefault)

        val office = store.save(address("Insurgentes 100"), makeDefault = true)
        assertEquals(office.id, store.preferred()?.id)
        assertEquals(listOf(office.id), store.getAll().filter { it.isDefault }.map { it.id })
    }

    @Test
    fun `the default can be changed on its own`() {
        val home = store.save(address("Reforma 222"), makeDefault = true)
        val office = store.save(address("Insurgentes 100"))

        store.setDefault(office.id)

        assertEquals(office.id, store.preferred()?.id)
        assertFalse(store.getAll().first { it.id == home.id }.isDefault)
    }

    @Test
    fun `without a default the most recently used address is preferred`() {
        store.save(address("Reforma 222"))
        val latest = store.save(address("Insurgentes 100"))

        assertEquals(latest.id, store.preferred()?.id)
    }

    @Test
    fun `addresses survive a restart of the app`() {
        store.save(address("Reforma 222"), label = "Home", makeDefault = true)

        val reopened = SavedAddressStore(database)

        assertEquals("Home", reopened.preferred()?.label)
    }

    @Test
    fun `an address can be forgotten, and so can all of them`() {
        val home = store.save(address("Reforma 222"))
        store.save(address("Insurgentes 100"))

        store.remove(home.id)
        assertEquals(listOf("Insurgentes 100"), store.getAll().map { it.address.street })

        store.clear()
        assertEquals(emptyList(), store.getAll())
    }

    @Test
    fun `an address is edited in place and keeps its position`() {
        val home = store.save(address("Reforma 222"), label = "Home")
        store.save(address("Insurgentes 100"))

        val edited = store.update(home.id, address("Reforma 300"), label = "Casa")

        assertEquals(home.id, edited?.id)
        assertEquals(listOf("Insurgentes 100", "Reforma 300"), store.getAll().map { it.address.street })
        assertEquals("Casa", store.getAll().last().label)
    }

    @Test
    fun `an edit can clear the label and make the address the default`() {
        val home = store.save(address("Reforma 222"), label = "Home")
        store.save(address("Insurgentes 100"), makeDefault = true)

        store.update(home.id, address("Reforma 222"), label = null, makeDefault = true)

        val preferred = store.preferred()
        assertEquals(home.id, preferred?.id)
        assertNull(preferred?.label)
        assertEquals(1, store.getAll().count { it.isDefault })
    }

    @Test
    fun `an edit that matches another saved address merges the two`() {
        val home = store.save(address("Reforma 222"))
        store.save(address("Insurgentes 100"), makeDefault = true)

        store.update(home.id, address("Insurgentes 100"), label = "Office")

        val all = store.getAll()
        assertEquals(listOf(home.id), all.map { it.id })
        assertTrue(all.single().isDefault, "the default survives the merge")
    }

    @Test
    fun `editing an address that is gone changes nothing`() {
        store.save(address("Reforma 222"))

        assertNull(store.update(999, address("Madero 1"), label = null))
        assertEquals(listOf("Reforma 222"), store.getAll().map { it.address.street })
    }

    @Test
    fun `a row that cannot be read is skipped, not a crash`() {
        store.save(address("Reforma 222"))
        database.savedAddressQueries.insertAddress(label = null, address = "{not json", last_used = 99)

        assertEquals(listOf("Reforma 222"), store.getAll().map { it.address.street })
    }
}
