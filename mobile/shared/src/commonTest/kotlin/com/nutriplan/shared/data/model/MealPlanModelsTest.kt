package com.nutriplan.shared.data.model

import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The meal plan models against payloads shaped exactly like `contracts/dietary.openapi.yaml`.
 *
 * (An earlier version of these tests only constructed the models, which is how a model that could
 * not decode a single real response went unnoticed.)
 */
class MealPlanModelsTest {

    /** Same settings as the app's HTTP client. */
    private val json = Json {
        isLenient = true
        ignoreUnknownKeys = true
        prettyPrint = false
        encodeDefaults = true
    }

    @Test
    fun `decodes a full plan response`() {
        val plan = json.decodeFromString<MealPlan>(FULL_PLAN)

        assertEquals("6f1c9a52-0b7e-4c1c-9d51-1f0f3c0a7e11", plan.id)
        assertEquals("Week 40", plan.name)
        assertEquals("2026-10-01", plan.startDate)
        assertEquals("2026-10-07", plan.endDate)
        assertEquals(2000, plan.dailyCalorieTarget)
        assertEquals("draft", plan.status)
        assertEquals(2, plan.meals.size)

        val breakfast = plan.meals[0]
        assertEquals("breakfast", breakfast.mealType)
        assertEquals(1.5, breakfast.servings)
        assertEquals(0, breakfast.dayIndex)
        assertNull(breakfast.recipe)
        assertEquals(450, breakfast.nutritionalInfo?.calories)
        assertEquals(20.5, breakfast.nutritionalInfo?.protein)

        val unassigned = plan.meals[1]
        assertNull(unassigned.dayIndex)
        assertEquals(4, unassigned.satisfactionLevel)
        assertNull(unassigned.nutritionalInfo)
    }

    @Test
    fun `decodes the nutritional summary with unknown values kept as null`() {
        val summary = json.decodeFromString<MealPlan>(FULL_PLAN).nutritionalSummary
        assertNotNull(summary)

        assertEquals(900, summary.total?.calories)
        assertEquals(128, summary.dailyAverage?.calories)
        assertNull(summary.dailyAverage?.protein)
        assertEquals(2000, summary.targets.calories)
        assertEquals(150, summary.targets.protein)
        assertNull(summary.targets.carbs)
        assertEquals(6.4, summary.progress.calories.percentOfTarget)
        assertEquals("under", summary.progress.calories.status)
        assertNull(summary.progress.protein.status)
    }

    @Test
    fun `decodes a list of summaries which carry no calorie target or meals`() {
        val plans = json.decodeFromString<List<MealPlanSummary>>(
            """
            [
              {"id":"p1","name":"Week 40","startDate":"2026-10-01","endDate":"2026-10-07","status":"active"},
              {"id":"p2","name":"Week 41","startDate":"2026-10-08","endDate":"2026-10-14","status":"draft"}
            ]
            """,
        )

        assertEquals(listOf("p1", "p2"), plans.map { it.id })
        assertEquals(listOf("active", "draft"), plans.map { it.status })
    }

    @Test
    fun `a plan response without the optional parts still decodes`() {
        val plan = json.decodeFromString<MealPlan>(
            """{"id":"p1","name":"Bare","startDate":"2026-10-01","endDate":"2026-10-01","dailyCalorieTarget":1800,"status":"saved"}""",
        )

        assertEquals(emptyList(), plan.meals)
        assertNull(plan.nutritionalSummary)
    }

    @Test
    fun `decodes the add meal response that embeds the recipe`() {
        val meal = json.decodeFromString<PlanMeal>(
            """
            {
              "id":"m3","mealType":"dinner","servings":2.0,"dayIndex":1,"satisfactionLevel":null,
              "recipe":{
                "id":"r1","name":"Lentil soup","description":"Warm","ingredients":[{"name":"lentils","quantity":200.0,"unit":"g"}],
                "instructions":["Boil"],"prepTime":10,"cookTime":30,"servings":4,"imageUrl":"https://example.com/a.jpg",
                "nutritionalInfo":{"calories":300,"protein":18.0,"carbs":40.0,"fat":5.0,"sugar":3.0},"dietaryTypes":["vegan"]
              },
              "nutritionalInfo":{"calories":600,"protein":36.0,"carbs":80.0,"fat":10.0,"sugar":6.0}
            }
            """,
        )

        assertEquals(PlanMealRecipe(id = "r1", name = "Lentil soup", imageUrl = "https://example.com/a.jpg"), meal.recipe)
        assertEquals(600, meal.nutritionalInfo?.calories)
    }

    @Test
    fun `create request uses the contract field names`() {
        val body = json.encodeToString(
            CreateMealPlanRequest(
                name = "Week 40",
                startDate = "2026-10-01",
                endDate = "2026-10-07",
                dailyCalorieTarget = 2000,
                macroTargets = DietaryMacroTargets(proteinGrams = 150),
                dietaryType = "vegan",
            ),
        )

        assertTrue("\"dailyCalorieTarget\":2000" in body, body)
        assertTrue("\"macroTargets\":{" in body && "\"proteinGrams\":150" in body, body)
        assertTrue("\"dietaryType\":\"vegan\"" in body, body)
        assertFalse("targetCalories" in body, body)
        assertFalse("dietaryPreferences" in body, body)
    }

    @Test
    fun `add meal request uses servings and a lowercase meal type`() {
        val body = json.encodeToString(AddMealRequest(mealType = "lunch", recipeId = "r1", servings = 1.5))

        assertEquals("""{"mealType":"lunch","recipeId":"r1","servings":1.5}""", body)
    }

    @Test
    fun `status change request carries only the status`() {
        assertEquals("""{"status":"active"}""", json.encodeToString(UpdateMealPlanStatusRequest("active")))
    }

    private companion object {
        val FULL_PLAN = """
            {
              "id":"6f1c9a52-0b7e-4c1c-9d51-1f0f3c0a7e11",
              "name":"Week 40",
              "startDate":"2026-10-01",
              "endDate":"2026-10-07",
              "dailyCalorieTarget":2000,
              "status":"draft",
              "meals":[
                {"id":"m1","mealType":"breakfast","servings":1.5,"dayIndex":0,"satisfactionLevel":null,"recipe":null,
                 "nutritionalInfo":{"calories":450,"protein":20.5,"carbs":60.0,"fat":12.0,"sugar":8.0}},
                {"id":"m2","mealType":"lunch","servings":1,"dayIndex":null,"satisfactionLevel":4,"recipe":null,"nutritionalInfo":null}
              ],
              "nutritionalSummary":{
                "total":{"calories":900,"protein":30.0,"carbs":70.0,"fat":20.0,"sugar":9.0},
                "dailyAverage":{"calories":128,"protein":null,"carbs":null,"fat":null,"sugar":null},
                "targets":{"calories":2000,"protein":150,"carbs":null,"fat":null,"sugar":null},
                "progress":{
                  "calories":{"target":2000.0,"actual":128.0,"percentOfTarget":6.4,"status":"under"},
                  "protein":{"target":null,"actual":null,"percentOfTarget":null,"status":null},
                  "carbs":{"target":null,"actual":null,"percentOfTarget":null,"status":null},
                  "fat":{"target":null,"actual":null,"percentOfTarget":null,"status":null},
                  "sugar":{"target":null,"actual":null,"percentOfTarget":null,"status":null}
                }
              }
            }
        """.trimIndent()
    }
}
