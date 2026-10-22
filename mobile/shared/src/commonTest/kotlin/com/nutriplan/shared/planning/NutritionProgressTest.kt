package com.nutriplan.shared.planning

import com.nutriplan.shared.data.model.NutrientProgress
import com.nutriplan.shared.data.model.NutritionalInfo
import com.nutriplan.shared.data.model.NutritionalProgress
import com.nutriplan.shared.data.model.NutritionalSummary
import com.nutriplan.shared.data.model.NutritionalTargets
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class NutritionProgressTest {

    private val full = NutritionalSummary(
        total = NutritionalInfo(calories = 12600, protein = 630.0, carbs = 1400.0, fat = 420.0),
        dailyAverage = NutritionalInfo(calories = 1800, protein = 90.0, carbs = 200.0, fat = 60.0),
        targets = NutritionalTargets(calories = 2000, protein = 90, carbs = 180, fat = 70),
        progress = NutritionalProgress(
            calories = NutrientProgress(2000.0, 1800.0, 90.0, "under"),
            protein = NutrientProgress(90.0, 90.0, 100.0, "on_target"),
            carbs = NutrientProgress(180.0, 200.0, 111.1, "over"),
            fat = NutrientProgress(70.0, 60.0, 85.7, "under"),
        ),
    )

    @Test
    fun `no summary has no rows and no data`() {
        val ui = (null as NutritionalSummary?).toNutritionSummaryUi()

        assertTrue(ui.rows.isEmpty())
        assertFalse(ui.hasData)
    }

    @Test
    fun `rows follow the display order and skip nutrients the summary does not report`() {
        val ui = full.toNutritionSummaryUi()

        assertEquals(
            listOf(Nutrient.CALORIES, Nutrient.PROTEIN, Nutrient.CARBS, Nutrient.FAT),
            ui.rows.map { it.nutrient },
        )
        assertNull(ui.row(Nutrient.SUGAR))
        assertTrue(ui.hasData)
    }

    @Test
    fun `the server's progress is used as sent`() {
        val calories = full.toNutritionSummaryUi().row(Nutrient.CALORIES)!!

        assertEquals(1800.0, calories.average)
        assertEquals(2000.0, calories.target)
        assertEquals(90.0, calories.percentOfTarget)
        assertEquals(ProgressStatus.UNDER, calories.status)
        assertEquals(12600.0, calories.total)
    }

    @Test
    fun `under on target and over are told apart`() {
        val ui = full.toNutritionSummaryUi()

        assertEquals(ProgressStatus.UNDER, ui.row(Nutrient.FAT)!!.status)
        assertEquals(ProgressStatus.ON_TARGET, ui.row(Nutrient.PROTEIN)!!.status)
        assertEquals(ProgressStatus.OVER, ui.row(Nutrient.CARBS)!!.status)
    }

    @Test
    fun `by how much a nutrient is over or under is only given for those states`() {
        val ui = full.toNutritionSummaryUi()

        assertEquals(20.0, ui.row(Nutrient.CARBS)!!.overBy)
        assertNull(ui.row(Nutrient.CARBS)!!.underBy)
        assertEquals(200.0, ui.row(Nutrient.CALORIES)!!.underBy)
        assertNull(ui.row(Nutrient.CALORIES)!!.overBy)
        assertNull(ui.row(Nutrient.PROTEIN)!!.overBy)
        assertNull(ui.row(Nutrient.PROTEIN)!!.underBy)
    }

    @Test
    fun `the bar is capped at full and never negative`() {
        val ui = full.toNutritionSummaryUi()

        assertEquals(1f, ui.row(Nutrient.CARBS)!!.barFraction, "an overshoot fills the bar")
        assertEquals(0.9f, ui.row(Nutrient.CALORIES)!!.barFraction)
        val negative = NutrientRow(Nutrient.FAT, 1.0, 1.0, -5.0, ProgressStatus.UNDER, null)
        assertEquals(0f, negative.barFraction)
    }

    @Test
    fun `a partial payload falls back to the plan's target and average and derives the rest`() {
        val partial = NutritionalSummary(
            dailyAverage = NutritionalInfo(calories = 2500),
            targets = NutritionalTargets(calories = 2000),
        )

        val calories = partial.toNutritionSummaryUi().row(Nutrient.CALORIES)!!

        assertEquals(2500.0, calories.average)
        assertEquals(2000.0, calories.target)
        assertEquals(125.0, calories.percentOfTarget)
        assertEquals(ProgressStatus.OVER, calories.status)
    }

    @Test
    fun `exactly at the target is on target like the server`() {
        val summary = NutritionalSummary(
            dailyAverage = NutritionalInfo(calories = 2000),
            targets = NutritionalTargets(calories = 2000),
        )

        assertEquals(ProgressStatus.ON_TARGET, summary.toNutritionSummaryUi().row(Nutrient.CALORIES)!!.status)
    }

    @Test
    fun `an unrecognised status falls back to the percentage`() {
        val summary = NutritionalSummary(
            progress = NutritionalProgress(calories = NutrientProgress(2000.0, 1000.0, 50.0, "mystery")),
        )

        assertEquals(ProgressStatus.UNDER, summary.toNutritionSummaryUi().row(Nutrient.CALORIES)!!.status)
    }

    @Test
    fun `an average without a target is unknown not 0 percent`() {
        val summary = NutritionalSummary(dailyAverage = NutritionalInfo(protein = 80.0))

        val protein = summary.toNutritionSummaryUi().row(Nutrient.PROTEIN)!!

        assertEquals(80.0, protein.average)
        assertNull(protein.target)
        assertNull(protein.percentOfTarget)
        assertNull(protein.barFraction)
        assertEquals(ProgressStatus.UNKNOWN, protein.status)
    }

    @Test
    fun `a zero target gives no percentage`() {
        val summary = NutritionalSummary(
            dailyAverage = NutritionalInfo(calories = 100),
            targets = NutritionalTargets(calories = 0),
        )

        val calories = summary.toNutritionSummaryUi().row(Nutrient.CALORIES)!!

        assertNull(calories.percentOfTarget)
        assertEquals(ProgressStatus.UNKNOWN, calories.status)
    }

    @Test
    fun `a target without an average still gets a row but no data`() {
        val summary = NutritionalSummary(targets = NutritionalTargets(calories = 2000))

        val ui = summary.toNutritionSummaryUi()

        assertNotNull(ui.row(Nutrient.CALORIES))
        assertNull(ui.row(Nutrient.CALORIES)!!.average)
        assertFalse(ui.hasData)
    }

    @Test
    fun `a sugar target shows up when set`() {
        val summary = NutritionalSummary(
            dailyAverage = NutritionalInfo(sugar = 30.0),
            targets = NutritionalTargets(sugar = 25),
        )

        val sugar = summary.toNutritionSummaryUi().row(Nutrient.SUGAR)!!

        assertEquals(ProgressStatus.OVER, sugar.status)
        assertEquals(5.0, sugar.overBy)
    }
}
