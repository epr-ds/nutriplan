package com.nutriplan.shared.data.local

import app.cash.sqldelight.db.SqlDriver

/**
 * Creates the platform SQLite driver for the local database.
 *
 * Android uses `AndroidSqliteDriver` (needs a `Context`); iOS uses `NativeSqliteDriver`.
 */
expect class DatabaseDriverFactory {
    fun createDriver(): SqlDriver
}
