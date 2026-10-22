package com.nutriplan.shared.data.local

import com.nutriplan.db.NutriPlanDatabase
import com.nutriplan.shared.data.model.OrderAddress
import kotlinx.serialization.json.Json

/** A delivery address the user saved, with an optional [label] ("Home") and whether it is the default. */
data class SavedAddress(
    val id: Long,
    val address: OrderAddress,
    val label: String? = null,
    val isDefault: Boolean = false,
)

/**
 * The user's delivery addresses, kept on the device (COM-503). The Commerce API has no address
 * resource -- each create-order request carries its own address -- so this is the address book
 * checkout offers from, and it works offline. Addresses come back with the default first, then the
 * most recently used; saving an address that is already there only moves it up.
 */
class SavedAddressStore(private val database: NutriPlanDatabase) {

    private val queries = database.savedAddressQueries

    /** Tolerant on read: a row written by an older app version must never crash the app. */
    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    /** Every saved address: the default first, then the most recently used. Unreadable rows are skipped. */
    fun getAll(): List<SavedAddress> =
        queries.selectAll().executeAsList().mapNotNull { row -> decode(row.id, row.label, row.address, row.is_default) }

    /** The default address, or the most recently used one when none is marked default; null when empty. */
    fun preferred(): SavedAddress? = getAll().firstOrNull()

    /**
     * Save [address] (or, when it is already saved, mark it as just used) and return it. A non-null
     * [label] replaces the saved one; [makeDefault] makes it the only default.
     */
    fun save(address: OrderAddress, label: String? = null, makeDefault: Boolean = false): SavedAddress {
        val text = json.encodeToString(OrderAddress.serializer(), address)
        val id = database.transactionWithResult {
            val next = (queries.selectLastUsed().executeAsOneOrNull() ?: 0L) + 1L
            val existing = queries.selectByAddress(text).executeAsOneOrNull()
            val id = if (existing != null) {
                queries.touch(last_used = next, id = existing.id)
                existing.id
            } else {
                queries.insertAddress(label = label, address = text, last_used = next)
                queries.lastInsertedId().executeAsOne()
            }
            if (label != null) queries.relabel(label = label, id = id)
            if (makeDefault) {
                queries.clearDefault()
                queries.markDefault(id)
            }
            id
        }
        val row = queries.selectById(id).executeAsOne()
        return SavedAddress(id = row.id, address = address, label = row.label, isDefault = row.is_default)
    }

    /** Make the address [id] the only default. */
    fun setDefault(id: Long) {
        database.transaction {
            queries.clearDefault()
            queries.markDefault(id)
        }
    }

    /** Forget one address. */
    fun remove(id: Long) {
        queries.deleteAddress(id)
    }

    /** Forget every address (for example on sign-out). */
    fun clear() {
        queries.deleteAll()
    }

    /** A stored row as a [SavedAddress], or null when its address cannot be read. */
    private fun decode(id: Long, label: String?, address: String, isDefault: Boolean): SavedAddress? =
        runCatching { json.decodeFromString(OrderAddress.serializer(), address) }.getOrNull()?.let { decoded ->
            SavedAddress(id = id, address = decoded, label = label, isDefault = isDefault)
        }
}
