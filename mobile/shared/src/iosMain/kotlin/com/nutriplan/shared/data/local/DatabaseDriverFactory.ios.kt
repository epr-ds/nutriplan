package com.nutriplan.shared.data.local

import app.cash.sqldelight.db.SqlDriver
import app.cash.sqldelight.driver.native.NativeSqliteDriver
import com.nutriplan.db.NutriPlanDatabase

actual class DatabaseDriverFactory {
    actual fun createDriver(): SqlDriver =
        NativeSqliteDriver(NutriPlanDatabase.Schema, DATABASE_NAME)

    private companion object {
        const val DATABASE_NAME = "nutriplan.db"
    }
}
