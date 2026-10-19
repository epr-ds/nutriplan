package com.nutriplan.shared.testing

import app.cash.sqldelight.driver.jdbc.sqlite.JdbcSqliteDriver
import com.nutriplan.db.NutriPlanDatabase
import com.nutriplan.shared.data.local.MealPlanCache
import com.nutriplan.shared.data.model.MealPlan
import com.nutriplan.shared.data.model.MealPlanSummary
import com.nutriplan.shared.data.model.NutritionalInfo
import com.nutriplan.shared.data.model.NutritionalSummary
import com.nutriplan.shared.data.model.NutritionalTargets
import com.nutriplan.shared.data.model.PlanMeal
import com.nutriplan.shared.data.model.PlanMealRecipe

/** A fresh in-memory SQLite database with the current schema. */
fun newDatabase(): NutriPlanDatabase {
    val driver = JdbcSqliteDriver(JdbcSqliteDriver.IN_MEMORY)
    NutriPlanDatabase.Schema.create(driver)
    return NutriPlanDatabase(driver)
}

fun newCache(): MealPlanCache = MealPlanCache(newDatabase())

fun summary(id: String, start: String = "2026-10-01", status: String = "active") = MealPlanSummary(
    id = id,
    name = "Plan $id",
    startDate = start,
    endDate = "2026-10-07",
    status = status,
)

fun meal(
    id: String,
    dayIndex: Int? = 0,
    type: String = "lunch",
    calories: Int? = 500,
    recipe: PlanMealRecipe? = null,
) = PlanMeal(
    id = id,
    mealType = type,
    servings = 1.5,
    dayIndex = dayIndex,
    satisfactionLevel = 4,
    recipe = recipe,
    nutritionalInfo = calories?.let { NutritionalInfo(calories = it, protein = 25.5, carbs = 40.0, fat = 12.0, sugar = 6.0) },
)

fun fullPlan(
    id: String,
    start: String = "2026-10-01",
    status: String = "active",
    meals: List<PlanMeal> = emptyList(),
    summary: NutritionalSummary? = null,
) = MealPlan(
    id = id,
    name = "Plan $id",
    startDate = start,
    endDate = "2026-10-07",
    dailyCalorieTarget = 2000,
    status = status,
    meals = meals,
    nutritionalSummary = summary,
)

fun nutritionalSummary() = NutritionalSummary(
    total = NutritionalInfo(calories = 900),
    dailyAverage = NutritionalInfo(calories = 128),
    targets = NutritionalTargets(calories = 2000, protein = 150),
)
