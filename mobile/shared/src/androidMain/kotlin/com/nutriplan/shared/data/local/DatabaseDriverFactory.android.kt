package com.nutriplan.shared.data.local

import android.content.Context
import app.cash.sqldelight.db.SqlDriver
import app.cash.sqldelight.driver.android.AndroidSqliteDriver
import com.nutriplan.db.NutriPlanDatabase

actual class DatabaseDriverFactory(private val context: Context) {
    actual fun createDriver(): SqlDriver =
        AndroidSqliteDriver(NutriPlanDatabase.Schema, context, DATABASE_NAME)

    private companion object {
        const val DATABASE_NAME = "nutriplan.db"
    }
}
